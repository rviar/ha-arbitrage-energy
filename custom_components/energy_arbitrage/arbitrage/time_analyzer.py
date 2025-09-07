"""
Time Window Analyzer for optimal arbitrage timing.
Analyzes price data to find optimal buy/sell windows with time constraints.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

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
    
    @property
    def is_current(self) -> bool:
        """True if window is happening now."""
        now = datetime.now(timezone.utc)
        # Use same logic as utils.get_current_price_data for consistency
        return self.start_time <= now < self.end_time
    
    @property
    def is_upcoming(self) -> bool:
        """True if window is in the future."""
        now = datetime.now(timezone.utc)
        return now < self.start_time
    
    @property
    def time_until_start(self) -> timedelta:
        """Time until window starts."""
        now = datetime.now(timezone.utc)
        return max(timedelta(0), self.start_time - now)
    
    @property
    def time_remaining(self) -> timedelta:
        """Time remaining in current window."""
        now = datetime.now(timezone.utc)
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
        self._price_history = []  # Cache for price data analysis
        
    def analyze_price_windows(self, price_data: Dict[str, Any], hours_ahead: int = 24) -> List[PriceWindow]:
        """Analyze price data to find optimal trading windows."""
        
        try:
            buy_prices = price_data.get("buy_prices", [])
            sell_prices = price_data.get("sell_prices", [])
            
            if not buy_prices or not sell_prices:
                _LOGGER.warning(f"Price data missing: buy_prices={len(buy_prices) if buy_prices else 0}, sell_prices={len(sell_prices) if sell_prices else 0}")
                _LOGGER.debug(f"Available price_data keys: {list(price_data.keys())}")
                return []
            
            # Debug current time and data range
            now = datetime.now(timezone.utc)
            _LOGGER.debug(f"🕐 Current UTC time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            if buy_prices:
                first_buy = buy_prices[0].get('start', 'unknown')
                last_buy = buy_prices[-1].get('start', 'unknown')
                _LOGGER.debug(f"📊 Buy data range: {first_buy} to {last_buy}")
            if sell_prices:
                first_sell = sell_prices[0].get('start', 'unknown')
                last_sell = sell_prices[-1].get('start', 'unknown')
                _LOGGER.debug(f"💰 Sell data range: {first_sell} to {last_sell}")
            
            # Find buy windows (low prices)
            buy_windows = self._find_low_price_windows(buy_prices, hours_ahead)
            
            # Find sell windows (high prices)
            sell_windows = self._find_high_price_windows(sell_prices, hours_ahead)
            
            # Combine and sort by urgency
            all_windows = buy_windows + sell_windows
            all_windows.sort(key=lambda w: (w.urgency != 'high', w.urgency != 'medium', w.start_time))
            
            return all_windows
            
        except Exception as e:
            _LOGGER.error(f"Error analyzing price windows: {e}")
            return []
    
    def _find_low_price_windows(self, buy_prices: List[Dict], hours_ahead: int) -> List[PriceWindow]:
        """Find windows of low prices suitable for buying/charging."""
        
        if not buy_prices:
            return []
        
        # Sort prices to find bottom quartile  
        sorted_prices = sorted(buy_prices, key=lambda p: p.get('value', float('inf')))
        quartile_size = max(1, len(sorted_prices) // 4)
        low_price_threshold = sorted_prices[quartile_size - 1].get('value', 0)
        
        # Find consecutive low-price periods
        windows = []
        current_window = None
        
        for price_point in buy_prices:
            try:
                price = price_point.get('value', float('inf'))  # 'value' instead of 'price'
                timestamp_str = price_point.get('start', '')    # 'start' instead of 'timestamp'
                
                # Parse timestamp using unified function
                from .utils import parse_datetime
                timestamp = parse_datetime(timestamp_str)
                if not timestamp:
                    _LOGGER.warning(f"Failed to parse buy timestamp: {timestamp_str}")
                    continue
                
                # Skip past prices
                now = datetime.now(timezone.utc)
                if timestamp < now:
                    continue
                
                # Skip prices too far in future
                if timestamp > now + timedelta(hours=hours_ahead):
                    continue
                
                # Check if price is low enough
                if price <= low_price_threshold * 1.1:  # 10% tolerance
                    
                    if current_window is None:
                        # Start new window
                        current_window = {
                            'start': timestamp,
                            'end': timestamp + timedelta(hours=1),  # Assume 1h periods
                            'price': price,
                            'count': 1
                        }
                    else:
                        # Extend current window if consecutive
                        if timestamp <= current_window['end']:
                            current_window['end'] = timestamp + timedelta(hours=1)
                            current_window['price'] = min(current_window['price'], price)
                            current_window['count'] += 1
                        else:
                            # Gap found, save current window and start new one
                            if current_window['count'] >= 1:  # At least 1 hour
                                windows.append(self._create_buy_window(current_window))
                            
                            current_window = {
                                'start': timestamp,
                                'end': timestamp + timedelta(hours=1),
                                'price': price,
                                'count': 1
                            }
                else:
                    # Price too high, end current window
                    if current_window and current_window['count'] >= 1:
                        windows.append(self._create_buy_window(current_window))
                    current_window = None
                    
            except Exception as e:
                _LOGGER.debug(f"Error processing price point: {e}")
                continue
        
        # Don't forget last window
        if current_window and current_window['count'] >= 1:
            windows.append(self._create_buy_window(current_window))
        
        return windows
    
    def _find_high_price_windows(self, sell_prices: List[Dict], hours_ahead: int) -> List[PriceWindow]:
        """Find windows of high prices suitable for selling/discharging."""
        
        if not sell_prices:
            return []
        
        # Sort prices to find top quartile
        sorted_prices = sorted(sell_prices, key=lambda p: p.get('value', 0), reverse=True)
        quartile_size = max(1, len(sorted_prices) // 4)
        high_price_threshold = sorted_prices[quartile_size - 1].get('value', float('inf'))
        
        # Find consecutive high-price periods
        windows = []
        current_window = None
        
        for price_point in sell_prices:
            try:
                price = price_point.get('value', 0)          # 'value' instead of 'price'
                timestamp_str = price_point.get('start', '')  # 'start' instead of 'timestamp'
                
                # Parse timestamp using unified function
                from .utils import parse_datetime
                timestamp = parse_datetime(timestamp_str)
                if not timestamp:
                    _LOGGER.warning(f"Failed to parse sell timestamp: {timestamp_str}")
                    continue
                
                # Skip past prices
                now = datetime.now(timezone.utc)
                if timestamp < now:
                    continue
                
                # Skip prices too far in future
                if timestamp > now + timedelta(hours=hours_ahead):
                    continue
                
                # Check if price is high enough
                if price >= high_price_threshold * 0.9:  # 10% tolerance
                    
                    if current_window is None:
                        # Start new window
                        current_window = {
                            'start': timestamp,
                            'end': timestamp + timedelta(hours=1),
                            'price': price,
                            'count': 1
                        }
                    else:
                        # Extend current window if consecutive
                        if timestamp <= current_window['end']:
                            current_window['end'] = timestamp + timedelta(hours=1)
                            current_window['price'] = max(current_window['price'], price)
                            current_window['count'] += 1
                        else:
                            # Gap found, save current window and start new one
                            if current_window['count'] >= 1:  # At least 1 hour
                                windows.append(self._create_sell_window(current_window))
                            
                            current_window = {
                                'start': timestamp,
                                'end': timestamp + timedelta(hours=1),
                                'price': price,
                                'count': 1
                            }
                else:
                    # Price too low, end current window
                    if current_window and current_window['count'] >= 1:
                        windows.append(self._create_sell_window(current_window))
                    current_window = None
                    
            except Exception as e:
                _LOGGER.debug(f"Error processing price point: {e}")
                continue
        
        # Don't forget last window
        if current_window and current_window['count'] >= 1:
            windows.append(self._create_sell_window(current_window))
        
        return windows
    
    def _create_buy_window(self, window_data: Dict) -> PriceWindow:
        """Create a buy price window."""
        duration = (window_data['end'] - window_data['start']).total_seconds() / 3600
        
        # Determine urgency based on timing and duration
        now = datetime.now(timezone.utc)
        time_until_start = (window_data['start'] - now).total_seconds() / 3600
        
        if time_until_start <= 1:
            urgency = 'high'    # Starting soon
        elif time_until_start <= 4:
            urgency = 'medium'  # Starting in a few hours
        else:
            urgency = 'low'     # Starting later
        
        return PriceWindow(
            action='buy',
            start_time=window_data['start'],
            end_time=window_data['end'],
            price=window_data['price'],
            duration_hours=duration,
            confidence=0.8,  # High confidence for price data
            urgency=urgency
        )
    
    def _create_sell_window(self, window_data: Dict) -> PriceWindow:
        """Create a sell price window."""
        duration = (window_data['end'] - window_data['start']).total_seconds() / 3600
        
        # Determine urgency based on timing and duration
        now = datetime.now(timezone.utc)
        time_until_start = (window_data['start'] - now).total_seconds() / 3600
        
        if time_until_start <= 1:
            urgency = 'high'    # Starting soon
        elif time_until_start <= 4:
            urgency = 'medium'  # Starting in a few hours
        else:
            urgency = 'low'     # Starting later
        
        return PriceWindow(
            action='sell',
            start_time=window_data['start'],
            end_time=window_data['end'],
            price=window_data['price'],
            duration_hours=duration,
            confidence=0.8,  # High confidence for price data
            urgency=urgency
        )
    
    def plan_battery_operation(self, 
                             target_energy_wh: float, 
                             action: str, 
                             windows: List[PriceWindow],
                             max_power_w: float) -> Optional[BatteryOperation]:
        """Plan a battery operation within available time windows."""
        
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
                
                # Calculate completion time
                completion_time = window.start_time + timedelta(hours=required_hours)
                
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
                feasible=max_energy >= target_energy_wh * 0.8,  # 80% of target is acceptable
                completion_time=best_window.end_time
            )
        
        return None
    
    def get_current_price_situation(self, windows: List[PriceWindow]) -> Dict[str, Any]:
        """Analyze current price situation and upcoming opportunities."""
        
        now = datetime.now(timezone.utc)
        
        # Find current windows
        current_windows = [w for w in windows if w.is_current]
        upcoming_windows = [w for w in windows if w.is_upcoming]
        
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
            if best_current.time_remaining.total_seconds() < 3600:  # < 1 hour
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
            if next_window.time_until_start.total_seconds() < 7200:  # < 2 hours
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
