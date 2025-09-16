"""
Time Window Analyzer for optimal arbitrage timing.
Analyzes price data to find optimal buy/sell windows with time constraints.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .utils import get_current_ha_time, get_ha_timezone, parse_datetime
from .constants import (
    TARGET_ENERGY_ACCEPTABLE_THRESHOLD, SECONDS_PER_HOUR
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
        # configurable number of top slots
        self._top_n_slots = 3
        
    @safe_execute(default_return=[])
    @log_performance
    def analyze_price_windows(self, price_data: Dict[str, Any], hours_ahead: int = 24) -> List[PriceWindow]:
        """Analyze price data by selecting top-N one-hour windows for buy/sell.

        Simplified approach:
        - For sell: pick top-N highest-price hours within horizon
        - For buy: pick top-N lowest-price hours within horizon
        - Return as one-hour `PriceWindow`s, deterministic ordering
        """
        buy_prices = price_data.get("buy_prices", [])
        sell_prices = price_data.get("sell_prices", [])

        if not buy_prices or not sell_prices:
            _LOGGER.warning(f"Price data missing: buy_prices={len(buy_prices) if buy_prices else 0}, sell_prices={len(sell_prices) if sell_prices else 0}")
            _LOGGER.debug(f"Available price_data keys: {list(price_data.keys())}")
            return []

        ha_tz = get_ha_timezone()
        now = datetime.now(ha_tz)
        horizon = now + timedelta(hours=hours_ahead)

        def _normalize(points: List[Dict]) -> List[tuple[datetime, datetime, float]]:
            normalized: List[tuple[datetime, datetime, float]] = []
            for p in points:
                try:
                    start = parse_datetime(p.get('start', ''))
                    end = parse_datetime(p.get('end', '')) if p.get('end') else (start + timedelta(hours=1) if start else None)
                    value = p.get('value', None)
                    if not start or end is None or value is None:
                        continue
                    # Filter to horizon, include current or future hours
                    if (end <= now) or (start > horizon):
                        continue
                    # Clamp to 1h blocks
                    duration_h = (end - start).total_seconds() / 3600.0
                    if duration_h <= 0:
                        continue
                    normalized.append((start, end, float(value)))
                except Exception:
                    continue
            return normalized

        norm_buy = _normalize(buy_prices)
        norm_sell = _normalize(sell_prices)

        # Select top-N by price with deterministic tiebreaker (earlier start first)
        norm_sell.sort(key=lambda x: (-x[2], x[0]))
        norm_buy.sort(key=lambda x: (x[2], x[0]))

        top_sell = norm_sell[: self._top_n_slots]
        top_buy = norm_buy[: self._top_n_slots]

        def _make_window(action: str, start: datetime, end: datetime, price: float) -> PriceWindow:
            duration = max(0.0, (end - start).total_seconds() / 3600.0)
            # Urgency based purely on time distance
            hours_until = max(0.0, (start - now).total_seconds() / 3600.0)
            if hours_until <= 1:
                urgency = 'high'
            elif hours_until <= 3:
                urgency = 'medium'
            else:
                urgency = 'low'
            base_conf = 0.85
            window = PriceWindow(
                action=action,
                start_time=start,
                end_time=end,
                price=float(price),
                duration_hours=duration or 1.0,
                confidence=base_conf,
                urgency=urgency
            )
            return window

        buy_windows = [_make_window('buy', s, e, p) for (s, e, p) in top_buy]
        sell_windows = [_make_window('sell', s, e, p) for (s, e, p) in top_sell]

        # Deterministic final ordering: earliest start first to aid scheduling
        all_windows = buy_windows + sell_windows
        all_windows.sort(key=lambda w: w.start_time)

        return all_windows
    
    # Removed legacy quartile-based window detection and peak-time algorithms
    # The top-3 approach returns one-hour windows already positioned at the hour start.
    # Keep minimal helpers only.
    
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
            
            # Select top-N by price, then allocate chronologically with reservation for later better windows
            sell_windows.sort(key=lambda w: (-w.price, w.start_time))
            if max_windows and max_windows > 0:
                sell_windows = sell_windows[:max_windows]
            # Chronological order for allocation
            chrono_windows = sorted(sell_windows, key=lambda w: w.start_time)
            remaining_wh = max(0.0, available_battery_wh)
            planned_ops: List[BatteryOperation] = []

            for idx, window in enumerate(chrono_windows):
                if remaining_wh <= 0:
                    break
                window_capacity_wh = max_power_w * max(0.0, window.duration_hours)
                if window_capacity_wh <= 0:
                    continue
                # Reserve energy for any future windows with higher prices
                future_better = [w for w in chrono_windows[idx+1:] if w.price > window.price]
                reserved_wh = sum(max_power_w * max(0.0, w.duration_hours) for w in future_better)
                allocatable_wh = max(0.0, remaining_wh - reserved_wh)
                allocate_wh = min(allocatable_wh, window_capacity_wh)
                if allocate_wh < 100:  # ignore tiny fragments
                    continue
                # Compute nominal power and duration in this window
                target_power_w = min(max_power_w, allocate_wh / max(0.001, window.duration_hours))
                duration_hours = allocate_wh / max(1.0, target_power_w)
                
                # Simplified: operate from window start
                optimal_start = window.start_time
                completion_time = window.start_time + timedelta(hours=duration_hours)
                
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
            
            # Select top-N by lowest price, then allocate chronologically with reservation for later better (lower price) windows
            buy_windows.sort(key=lambda w: (w.price, w.start_time))
            if max_windows and max_windows > 0:
                buy_windows = buy_windows[:max_windows]
            chrono_windows = sorted(buy_windows, key=lambda w: w.start_time)
            remaining_wh = max(0.0, headroom_wh)
            planned_ops: List[BatteryOperation] = []

            for idx, window in enumerate(chrono_windows):
                if remaining_wh <= 0:
                    break
                window_capacity_wh = max_power_w * max(0.0, window.duration_hours)
                if window_capacity_wh <= 0:
                    continue
                # Reserve headroom for any future windows with lower prices (better)
                future_better = [w for w in chrono_windows[idx+1:] if w.price < window.price]
                reserved_wh = sum(max_power_w * max(0.0, w.duration_hours) for w in future_better)
                allocatable_wh = max(0.0, remaining_wh - reserved_wh)
                allocate_wh = min(allocatable_wh, window_capacity_wh)
                if allocate_wh < 100:
                    continue
                target_power_w = min(max_power_w, allocate_wh / max(0.001, window.duration_hours))
                duration_hours = allocate_wh / max(1.0, target_power_w)
                
                # Simplified: operate from window start
                optimal_start = window.start_time
                completion_time = window.start_time + timedelta(hours=duration_hours)
                
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
