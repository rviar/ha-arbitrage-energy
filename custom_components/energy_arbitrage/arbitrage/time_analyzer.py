"""
Time Window Analyzer for optimal arbitrage timing.
Analyzes price data to find optimal buy/sell windows with time constraints.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from .utils import get_current_ha_time, get_ha_timezone, parse_datetime
from .constants import (
    PRICE_QUARTILE_DIVISOR, PRICE_TOLERANCE_HIGH_MULTIPLIER, PRICE_TOLERANCE_LOW_MULTIPLIER,
    URGENCY_HIGH_THRESHOLD_HOURS, URGENCY_MEDIUM_THRESHOLD_HOURS,
    PEAK_TIMES_TOP_N, TARGET_ENERGY_ACCEPTABLE_THRESHOLD, SECONDS_PER_HOUR
)
from .exceptions import safe_execute, log_performance

_LOGGER = logging.getLogger(__name__)

@dataclass
class PriceWindow:
    """Represents a time window for price-based operations."""
    action: str                    # "buy" | "sell" 
    start_time: datetime          # Window start
    end_time: datetime            # Window end  
    price: float                  # Price during window
    duration_hours: float         # Window duration in hours
    confidence: float             # Forecast confidence 0-1
    urgency: str                  # "low" | "medium" | "high"
    peak_times: List[Tuple[datetime, float]] = None  # (timestamp, price) for peaks within window
    
    @property
    def is_current(self) -> bool:
        """True if window is happening now."""
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        # Use same logic as utils.get_current_price_data for consistency
        return self.start_time <= now < self.end_time
    
    @property
    def is_upcoming(self) -> bool:
        """True if window is in the future."""
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        return now < self.start_time
    
    @property
    def time_until_start(self) -> timedelta:
        """Time until window starts."""
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        return max(timedelta(0), self.start_time - now)
    
    @property
    def time_remaining(self) -> timedelta:
        """Time remaining in current window."""
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        if self.is_current:
            return max(timedelta(0), self.end_time - now)
        return timedelta(0)
    
    def max_energy_capacity(self, battery_power_w: float) -> float:
        """Calculate max energy that can be moved during this window."""
        return battery_power_w * self.duration_hours  # Wh


@dataclass
class BatteryOperation:
    """Planned battery operation with timing."""
    action: str                   # "charge" | "discharge"
    target_energy_wh: float      # Energy to move
    target_power_w: float        # Required power 
    duration_hours: float        # Required time
    window: PriceWindow          # Associated price window
    feasible: bool               # Can be completed in time
    completion_time: datetime    # When operation will finish


class TimeWindowAnalyzer:
    """Analyzes price data to find optimal trading windows."""
    
    def __init__(self, sensor_helper):
        self.sensor_helper = sensor_helper
        
    @safe_execute(default_return=[])
    @log_performance
    def analyze_price_windows(self, price_data: Dict[str, Any], hours_ahead: int = 24) -> List[PriceWindow]:
        """Analyze price data to find optimal trading windows."""
        
        buy_prices = price_data.get("buy_prices", [])
        sell_prices = price_data.get("sell_prices", [])
        
        if not buy_prices or not sell_prices:
            _LOGGER.warning(f"Price data missing: buy_prices={len(buy_prices) if buy_prices else 0}, sell_prices={len(sell_prices) if sell_prices else 0}")
            _LOGGER.debug(f"Available price_data keys: {list(price_data.keys())}")
            return []
        
        # Find buy windows (low prices) and pass price data for peak analysis
        buy_windows = self._find_low_price_windows(buy_prices, hours_ahead, price_data=buy_prices)
        
        # Find sell windows (high prices) and pass price data for peak analysis
        sell_windows = self._find_high_price_windows(sell_prices, hours_ahead, price_data=sell_prices)
        
        # Combine and sort by urgency
        all_windows = buy_windows + sell_windows
        all_windows.sort(key=lambda w: (w.urgency != 'high', w.urgency != 'medium', w.start_time))
        
        return all_windows
    
    def _find_price_windows(self, prices: List[Dict], hours_ahead: int, 
                           action_type: str, price_data: List[Dict] = None) -> List[PriceWindow]:
        """Unified method to find price windows for both buying and selling."""
        
        if not prices:
            return []
        
        # Determine quartile and threshold based on action type
        is_buy = action_type == 'buy'
        
        if is_buy:
            # Sort prices to find bottom quartile for buying
            sorted_prices = sorted(prices, key=lambda p: p.get('value', float('inf')))
            quartile_size = max(1, len(sorted_prices) // PRICE_QUARTILE_DIVISOR)
            threshold = sorted_prices[quartile_size - 1].get('value', 0)
            multiplier = PRICE_TOLERANCE_HIGH_MULTIPLIER  # 1.1 for buy (allow 10% higher)
        else:
            # Sort prices to find top quartile for selling
            sorted_prices = sorted(prices, key=lambda p: p.get('value', 0), reverse=True)
            quartile_size = max(1, len(sorted_prices) // PRICE_QUARTILE_DIVISOR)
            threshold = sorted_prices[quartile_size - 1].get('value', float('inf'))
            multiplier = PRICE_TOLERANCE_LOW_MULTIPLIER   # 0.9 for sell (allow 10% lower)
                    
        # Find consecutive price periods that meet criteria
        windows = []
        current_window = None
        # Precompute HA now and horizon once
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        horizon = now + timedelta(hours=hours_ahead)
        
        for price_point in prices:
            try:
                price = price_point.get('value', float('inf') if is_buy else 0)
                timestamp_str = price_point.get('start', '')
                
                # Parse timestamp using unified function
                timestamp = parse_datetime(timestamp_str)
                if not timestamp:
                    _LOGGER.warning(f"Failed to parse {action_type} timestamp: {timestamp_str}")
                    continue
                
                # Skip past prices
                if timestamp < now:
                    continue
                
                # Skip prices too far in future
                if timestamp > horizon:
                    continue
                
                # Check if price meets criteria
                price_meets_criteria = (
                    price <= threshold * multiplier if is_buy else 
                    price >= threshold * multiplier
                )
                
                if price_meets_criteria:
                    if current_window is None:
                        # Start new window
                        current_window = {
                            'start': timestamp,
                            'end': timestamp + timedelta(hours=1),
                            'price': price
                        }
                    else:
                        # Extend current window if consecutive
                        if timestamp <= current_window['end']:
                            current_window['end'] = timestamp + timedelta(hours=1)
                            # For buy: take minimum price, for sell: take maximum price
                            current_window['price'] = (
                                min(current_window['price'], price) if is_buy else 
                                max(current_window['price'], price)
                            )
                        else:
                            # Gap found, save current window and start new one
                            window = (
                                self._create_buy_window(current_window, price_data) if is_buy else
                                self._create_sell_window(current_window, price_data)
                            )
                            windows.append(window)
                            
                            current_window = {
                                'start': timestamp,
                                'end': timestamp + timedelta(hours=1),
                                'price': price
                            }
                else:
                    if current_window:
                        window = (
                            self._create_buy_window(current_window, price_data) if is_buy else
                            self._create_sell_window(current_window, price_data)
                        )
                        windows.append(window)
                    current_window = None
                    
            except Exception as e:
                _LOGGER.debug(f"Error processing price point: {e}")
                continue
        
        # Don't forget last window
        if current_window:
            window = (
                self._create_buy_window(current_window, price_data) if is_buy else
                self._create_sell_window(current_window, price_data)
            )
            windows.append(window)
        
        return windows

    def _find_low_price_windows(self, buy_prices: List[Dict], hours_ahead: int, price_data: List[Dict] = None) -> List[PriceWindow]:
        return self._find_price_windows(buy_prices, hours_ahead, 'buy', price_data)
    
    def _find_high_price_windows(self, sell_prices: List[Dict], hours_ahead: int, price_data: List[Dict] = None) -> List[PriceWindow]:
        return self._find_price_windows(sell_prices, hours_ahead, 'sell', price_data)
    
    def _create_buy_window(self, window_data: Dict, price_data: List[Dict] = None) -> PriceWindow:
        duration = (window_data['end'] - window_data['start']).total_seconds() / 3600
        
        # Determine urgency based on timing and duration
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        time_until_start = (window_data['start'] - now).total_seconds() / 3600
        
        if time_until_start <= URGENCY_HIGH_THRESHOLD_HOURS:
            urgency = 'high'    # Starting soon
        elif time_until_start <= URGENCY_MEDIUM_THRESHOLD_HOURS:
            urgency = 'medium'  # Starting in a few hours
        else:
            urgency = 'low'     # Starting later
        
        # Calculate dynamic confidence based on window quality
        base_confidence = 0.8
        confidence = self._calculate_window_confidence(base_confidence, window_data, urgency, duration, price_data)
        
        # Create preliminary window to find peak times
        window = PriceWindow(
            action='buy',
            start_time=window_data['start'],
            end_time=window_data['end'],
            price=window_data['price'],
            duration_hours=duration,
            confidence=confidence,  # Dynamic confidence based on data quality
            urgency=urgency,
            peak_times=None  # Will be populated below
        )
        
        # Find peak times within this window if price_data is available
        if price_data:
            peak_times = self.find_peak_times_in_window(window, price_data, top_n=PEAK_TIMES_TOP_N)
            window.peak_times = peak_times
        else:
            _LOGGER.warning(f"⚠️ BUY window: price_data отсутствует для окна {window.start_time.strftime('%H:%M')}-{window.end_time.strftime('%H:%M')}")
        
        return window
    
    def _create_sell_window(self, window_data: Dict, price_data: List[Dict] = None) -> PriceWindow:
        """Create a sell price window."""
        duration = (window_data['end'] - window_data['start']).total_seconds() / 3600
        
        # Determine urgency based on timing and duration
        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        time_until_start = (window_data['start'] - now).total_seconds() / 3600
        
        if time_until_start <= URGENCY_HIGH_THRESHOLD_HOURS:
            urgency = 'high'    # Starting soon
        elif time_until_start <= URGENCY_MEDIUM_THRESHOLD_HOURS:
            urgency = 'medium'  # Starting in a few hours
        else:
            urgency = 'low'     # Starting later
        
        # Calculate dynamic confidence based on window quality
        base_confidence = 0.8
        confidence = self._calculate_window_confidence(base_confidence, window_data, urgency, duration, price_data)
        
        # Create preliminary window to find peak times
        window = PriceWindow(
            action='sell',
            start_time=window_data['start'],
            end_time=window_data['end'],
            price=window_data['price'],
            duration_hours=duration,
            confidence=confidence,  # Dynamic confidence based on data quality
            urgency=urgency,
            peak_times=None  # Will be populated below
        )
        
        # Find peak times within this window if price_data is available
        if price_data:
            peak_times = self.find_peak_times_in_window(window, price_data, top_n=PEAK_TIMES_TOP_N)
            window.peak_times = peak_times
        else:
            _LOGGER.warning(f"⚠️ SELL window: price_data отсутствует для окна {window.start_time.strftime('%H:%M')}-{window.end_time.strftime('%H:%M')}")
        
        return window
    
    def _calculate_window_confidence(self, base_confidence: float, window_data: Dict, 
                                    urgency: str, duration_hours: float, 
                                    price_data: List[Dict] = None) -> float:
        """Calculate dynamic confidence based on window quality factors."""
        confidence = base_confidence
        
        # Adjust based on urgency (higher urgency = lower confidence due to time pressure)
        urgency_multipliers = {
            'high': 0.9,    # High urgency = slightly lower confidence
            'medium': 1.0,  # Medium urgency = base confidence  
            'low': 1.1      # Low urgency = higher confidence (more time to plan)
        }
        confidence *= urgency_multipliers.get(urgency, 1.0)
        
        # Adjust based on window duration (longer windows = higher confidence)
        if duration_hours >= 4:
            confidence *= 1.1  # Long windows = higher confidence
        elif duration_hours <= 1:
            confidence *= 0.9  # Short windows = lower confidence
        
        # Adjust based on data availability
        if price_data:
            data_points = len(price_data)
            if data_points >= 24:  # Full day of data
                confidence *= 1.05
            elif data_points < 6:   # Limited data
                confidence *= 0.85
        else:
            confidence *= 0.8  # No peak data available
        
        # Time distance factor (closer = higher confidence)
        if 'start' in window_data:
            ha_tz = get_ha_timezone()
            now = datetime.now(ha_tz)
            hours_until = (window_data['start'] - now).total_seconds() / 3600
            
            if hours_until <= 2:    # Very soon
                confidence *= 1.1
            elif hours_until >= 24: # Far in future
                confidence *= 0.9
        
        # Clamp between reasonable bounds
        confidence = max(0.5, min(0.95, confidence))
        return confidence
    
    def find_peak_times_in_window(self, window: PriceWindow, 
                                  price_data: List[Dict], 
                                  top_n: int = PEAK_TIMES_TOP_N) -> List[Tuple[datetime, float]]:
        """Find peak price times within a specific window.
        
        For sell windows: finds times with highest prices
        For buy windows: finds times with lowest prices
        
        Args:
            window: The price window to analyze
            price_data: List of price data points with 'start' and 'value' keys
            top_n: Number of top times to return
            
        Returns:
            List of (timestamp, price) tuples sorted by price optimality
        """
        if not price_data:
            return []
            
        # Extract times and prices within the window
        peak_times = []
        found_in_window = 0
        total_checked = 0
        for price_point in price_data:
            try:
                total_checked += 1
                timestamp_str = price_point.get('start', '')
                price = price_point.get('value', 0)
                
                # Parse timestamp
                timestamp = parse_datetime(timestamp_str)
                if not timestamp:
                    continue
                
                # Check if timestamp is within window bounds
                if window.start_time <= timestamp <= window.end_time:
                    peak_times.append((timestamp, price))
                    found_in_window += 1
                    
            except Exception as e:
                _LOGGER.debug(f"Error processing price point in window analysis: {e}")
                continue
        
        
        if not peak_times:
            return []
        
        # Sort by price optimality
        if window.action == 'sell':
            # For selling: highest prices first (descending)
            peak_times.sort(key=lambda x: x[1], reverse=True)
        else:
            # For buying: lowest prices first (ascending)  
            peak_times.sort(key=lambda x: x[1])
        
        return peak_times[:top_n]
    
    def get_optimal_operation_time(self, window: PriceWindow, 
                                   price_data: List[Dict],
                                   operation_duration_hours: float = 1.0) -> Tuple[datetime, float]:
        """Get the optimal start time for an operation within a window.
        
        Args:
            window: The price window to analyze
            price_data: List of price data points
            operation_duration_hours: How long the operation will take
            
        Returns:
            Tuple of (optimal_start_time, expected_price)
        """
        peak_times = self.find_peak_times_in_window(window, price_data, top_n=5)
        
        if not peak_times:
            # Fallback to window start
            return window.start_time, window.price
            
        # Find the best time that allows completion within window
        for optimal_time, price in peak_times:
            completion_time = optimal_time + timedelta(hours=operation_duration_hours)
            
            # Check if operation can complete within window
            if completion_time <= window.end_time:
                return optimal_time, price
        
        # If no peak time works, use earliest time in window that fits
        earliest_start = window.end_time - timedelta(hours=operation_duration_hours)
        if earliest_start >= window.start_time:
            # Find price at earliest viable start time
            for timestamp, price in peak_times:
                if timestamp >= earliest_start:
                    _LOGGER.info(f"⚡ FALLBACK TIME: {window.action} operation at {timestamp.strftime('%H:%M')} "
                               f"(price: {price:.4f}, duration: {operation_duration_hours:.1f}h)")
                    return timestamp, price
                    
        # Last resort: use window start
        _LOGGER.warning(f"⚠️ Using window start time as fallback: {window.start_time.strftime('%H:%M')}")
        return window.start_time, window.price
    
    def plan_battery_operation(self, 
                             target_energy_wh: float, 
                             action: str, 
                             windows: List[PriceWindow],
                             max_power_w: float,
                             price_data: List[Dict] = None) -> Optional[BatteryOperation]:
        """Plan a battery operation within available time windows with optimal timing."""
        
        # Filter windows for the requested action
        relevant_windows = [w for w in windows if w.action == action]
        
        if not relevant_windows:
            return None
        
        # Sort by urgency and start time
        relevant_windows.sort(key=lambda w: (w.urgency != 'high', w.urgency != 'medium', w.start_time))
        
        for window in relevant_windows:
            
            # Calculate required time for operation
            required_hours = target_energy_wh / max_power_w
            
            # Check if window is long enough
            if window.duration_hours >= required_hours:
                
                # Calculate actual power needed (might be less than max)
                optimal_power = min(max_power_w, target_energy_wh / window.duration_hours)
                
                # 🚀 NEW: Find optimal start time within window
                if price_data:
                    optimal_start_time, _ = self.get_optimal_operation_time(
                        window, price_data, required_hours
                    )
                else:
                    # Fallback to window start if no price data
                    optimal_start_time = window.start_time
                
                # Calculate completion time from optimal start
                completion_time = optimal_start_time + timedelta(hours=required_hours)
                
                return BatteryOperation(
                    action=action,
                    target_energy_wh=target_energy_wh,
                    target_power_w=optimal_power,
                    duration_hours=required_hours,
                    window=window,
                    feasible=True,
                    completion_time=completion_time
                )
        
        # No suitable window found
        if relevant_windows:
            # Return best window even if not ideal
            best_window = relevant_windows[0]
            max_energy = best_window.max_energy_capacity(max_power_w)
            
            return BatteryOperation(
                action=action,
                target_energy_wh=min(target_energy_wh, max_energy),
                target_power_w=max_power_w,
                duration_hours=best_window.duration_hours,
                window=best_window,
                feasible=max_energy >= target_energy_wh * TARGET_ENERGY_ACCEPTABLE_THRESHOLD,  # 80% of target is acceptable
                completion_time=best_window.end_time
            )
        
        return None
    
    def get_current_price_situation(self, windows: List[PriceWindow]) -> Dict[str, Any]:
        """Analyze current price situation and upcoming opportunities."""
        # Debug: log current HA time for alignment checks
        now = get_current_ha_time()
        _LOGGER.debug(f"PriceSituation now: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Find current windows
        current_windows = [w for w in windows if w.is_current]
        upcoming_windows = [w for w in windows if w.is_upcoming]

        # Debug: log first two current and upcoming windows
        if current_windows:
            try:
                cur_preview = ", ".join(
                    f"{w.action} {w.start_time.strftime('%H:%M')}-{w.end_time.strftime('%H:%M')} @ {w.price:.4f}"
                    for w in current_windows[:2]
                )
                _LOGGER.debug(f"Current windows ({len(current_windows)}): {cur_preview}")
            except Exception:
                pass
        if upcoming_windows:
            try:
                up_preview = ", ".join(
                    f"{w.action} {w.start_time.strftime('%H:%M')}-{w.end_time.strftime('%H:%M')} @ {w.price:.4f}"
                    for w in upcoming_windows[:2]
                )
                _LOGGER.debug(f"Upcoming windows ({len(upcoming_windows)}): {up_preview}")
            except Exception:
                pass
        
        # Sort upcoming by start time
        upcoming_windows.sort(key=lambda w: w.start_time)
        
        situation = {
            'current_opportunities': len(current_windows),
            'upcoming_opportunities': len(upcoming_windows),
            'immediate_action': None,
            'next_opportunity': None,
            'time_pressure': 'low'
        }
        
        # Check current windows
        if current_windows:
            # Sort by urgency and price quality
            current_windows.sort(key=lambda w: (w.urgency != 'high', w.price if w.action == 'sell' else -w.price))
            
            best_current = current_windows[0]
            situation['immediate_action'] = {
                'action': best_current.action,
                'price': best_current.price,
                'time_remaining': best_current.time_remaining.total_seconds() / 3600,
                'urgency': best_current.urgency
            }
            
            # High time pressure if current window ends soon
            if best_current.time_remaining.total_seconds() < SECONDS_PER_HOUR:  # < 1 hour
                situation['time_pressure'] = 'high'
        
        # Check upcoming windows
        if upcoming_windows:
            next_window = upcoming_windows[0]
            situation['next_opportunity'] = {
                'action': next_window.action,
                'price': next_window.price,
                'time_until_start': next_window.time_until_start.total_seconds() / 3600,
                'duration': next_window.duration_hours,
                'urgency': next_window.urgency
            }
            
            # Medium pressure if next opportunity is soon
            if next_window.time_until_start.total_seconds() < (2 * SECONDS_PER_HOUR):  # < 2 hours
                situation['time_pressure'] = max(situation['time_pressure'], 'medium')
        
        return situation
    
    def optimize_operation_sequence(self, 
                                  operations: List[BatteryOperation],
                                  battery_capacity_wh: float,
                                  current_battery_level: float) -> List[BatteryOperation]:
        """Optimize sequence of battery operations for maximum efficiency."""
        
        if not operations:
            return []
        
        # Sort operations by start time
        operations.sort(key=lambda op: op.window.start_time)
        
        # Track battery state through operations
        current_energy_wh = (current_battery_level / 100) * battery_capacity_wh
        optimized_ops = []
        
        for operation in operations:
            
            # Check if operation is feasible given current battery state
            if operation.action == 'charge':
                max_charge_energy = battery_capacity_wh - current_energy_wh
                if max_charge_energy > 100:  # At least 100Wh worth charging
                    actual_energy = min(operation.target_energy_wh, max_charge_energy)
                    
                    # Update operation with actual energy
                    optimized_op = BatteryOperation(
                        action=operation.action,
                        target_energy_wh=actual_energy,
                        target_power_w=min(operation.target_power_w, actual_energy / operation.duration_hours),
                        duration_hours=actual_energy / operation.target_power_w,
                        window=operation.window,
                        feasible=True,
                        completion_time=operation.completion_time
                    )
                    
                    optimized_ops.append(optimized_op)
                    current_energy_wh += actual_energy
            
            elif operation.action == 'discharge':
                max_discharge_energy = current_energy_wh - (battery_capacity_wh * 0.2)  # Keep 20% reserve
                if max_discharge_energy > 100:  # At least 100Wh worth discharging
                    actual_energy = min(operation.target_energy_wh, max_discharge_energy)
                    
                    # Update operation with actual energy
                    optimized_op = BatteryOperation(
                        action=operation.action,
                        target_energy_wh=actual_energy,
                        target_power_w=min(operation.target_power_w, actual_energy / operation.duration_hours),
                        duration_hours=actual_energy / operation.target_power_w,
                        window=operation.window,
                        feasible=True,
                        completion_time=operation.completion_time
                    )
                    
                    optimized_ops.append(optimized_op)
                    current_energy_wh -= actual_energy
        
        return optimized_ops

    def plan_best_sell_schedule(
        self,
        windows: List[PriceWindow],
        available_battery_wh: float,
        battery_capacity_wh: float,
        current_battery_level_percent: float,
        min_reserve_percent: float,
        max_power_w: float,
        price_data: List[Dict] = None,
        max_windows: int = 4
    ) -> List[BatteryOperation]:
        """Allocate discharge across top-priced sell windows.
        
        - Ranks sell windows by price (desc), then start time
        - Allocates energy respecting max power and window durations
        - Honors reserve by later optimization step
        - Optionally shifts start to peak times within each window
        """
        try:
            sell_windows = [w for w in windows if getattr(w, 'action', None) == 'sell']
            if not sell_windows or available_battery_wh <= 0 or max_power_w <= 0:
                return []
            
            # Sort: best price first, break ties by earlier start
            sell_windows.sort(key=lambda w: (-w.price, w.start_time))
            if max_windows and max_windows > 0:
                sell_windows = sell_windows[:max_windows]
            
            remaining_wh = max(0.0, available_battery_wh)
            planned_ops: List[BatteryOperation] = []
            
            for window in sell_windows:
                if remaining_wh <= 0:
                    break
                window_capacity_wh = max_power_w * max(0.0, window.duration_hours)
                if window_capacity_wh <= 0:
                    continue
                allocate_wh = min(remaining_wh, window_capacity_wh)
                if allocate_wh < 100:  # ignore tiny fragments
                    continue
                # Compute nominal power and duration in this window
                target_power_w = min(max_power_w, allocate_wh / max(0.001, window.duration_hours))
                duration_hours = allocate_wh / max(1.0, target_power_w)
                
                # Try to shift to best time inside the window
                optimal_start, _ = self.get_optimal_operation_time(
                    window, price_data or [], operation_duration_hours=duration_hours
                )
                completion_time = optimal_start + timedelta(hours=duration_hours)
                
                planned_ops.append(BatteryOperation(
                    action='discharge',
                    target_energy_wh=allocate_wh,
                    target_power_w=target_power_w,
                    duration_hours=duration_hours,
                    window=window,
                    feasible=True,
                    completion_time=completion_time
                ))
                remaining_wh -= allocate_wh
            
            if not planned_ops:
                return []
            
            # Enforce reserve and feasibility over time
            optimized = self.optimize_operation_sequence(
                planned_ops,
                battery_capacity_wh=battery_capacity_wh,
                current_battery_level=current_battery_level_percent
            )
            return optimized
        except Exception as e:
            _LOGGER.warning(f"Failed to build best sell schedule: {e}")
            return []

    def plan_best_buy_schedule(
        self,
        windows: List[PriceWindow],
        headroom_wh: float,
        battery_capacity_wh: float,
        current_battery_level_percent: float,
        max_power_w: float,
        price_data: List[Dict] = None,
        max_windows: int = 4
    ) -> List[BatteryOperation]:
        """Allocate charging across lowest-priced buy windows.
        
        - Ranks buy windows by price (asc), then start time
        - Allocates energy up to battery headroom and window power/time limits
        - Shifts to intrawindow lowest price times where possible
        """
        try:
            buy_windows = [w for w in windows if getattr(w, 'action', None) == 'buy']
            if not buy_windows or headroom_wh <= 0 or max_power_w <= 0:
                return []
            
            # Sort: lowest price first, then earlier start
            buy_windows.sort(key=lambda w: (w.price, w.start_time))
            if max_windows and max_windows > 0:
                buy_windows = buy_windows[:max_windows]
            
            remaining_wh = max(0.0, headroom_wh)
            planned_ops: List[BatteryOperation] = []
            
            for window in buy_windows:
                if remaining_wh <= 0:
                    break
                window_capacity_wh = max_power_w * max(0.0, window.duration_hours)
                if window_capacity_wh <= 0:
                    continue
                allocate_wh = min(remaining_wh, window_capacity_wh)
                if allocate_wh < 100:
                    continue
                target_power_w = min(max_power_w, allocate_wh / max(0.001, window.duration_hours))
                duration_hours = allocate_wh / max(1.0, target_power_w)
                
                optimal_start, _ = self.get_optimal_operation_time(
                    window, price_data or [], operation_duration_hours=duration_hours
                )
                completion_time = optimal_start + timedelta(hours=duration_hours)
                
                planned_ops.append(BatteryOperation(
                    action='charge',
                    target_energy_wh=allocate_wh,
                    target_power_w=target_power_w,
                    duration_hours=duration_hours,
                    window=window,
                    feasible=True,
                    completion_time=completion_time
                ))
                remaining_wh -= allocate_wh
            
            if not planned_ops:
                return []
            
            optimized = self.optimize_operation_sequence(
                planned_ops,
                battery_capacity_wh=battery_capacity_wh,
                current_battery_level=current_battery_level_percent
            )
            return optimized
        except Exception as e:
            _LOGGER.warning(f"Failed to build best buy schedule: {e}")
            return []
