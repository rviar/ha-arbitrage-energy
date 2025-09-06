import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from .sensor_data_helper import SensorDataHelper
from .utils import (
    safe_float, calculate_available_battery_capacity, 
    get_current_price_data, find_price_extremes,
    calculate_arbitrage_profit, calculate_battery_charge_time
)

_LOGGER = logging.getLogger(__name__)

class ArbitrageOptimizer:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.sensor_helper = SensorDataHelper(coordinator.hass, coordinator.entry.entry_id)

    async def calculate_optimal_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Log current state for debugging
            self.sensor_helper.log_current_state()
            
            current_state = self._analyze_current_state_from_sensors()
            arbitrage_opportunities = self._find_arbitrage_opportunities_from_sensors(data)
            
            decision = self._make_decision_from_sensors(current_state, arbitrage_opportunities, data)
            
            _LOGGER.info(
                f"Arbitrage decision: {decision['action']} - {decision['reason']}"
                f" (Battery: {current_state['battery_level']:.1f}%, "
                f"Solar: {current_state['pv_power']:.0f}W, "
                f"Load: {current_state['load_power']:.0f}W)"
            )
            
            return decision
            
        except Exception as e:
            _LOGGER.error(f"Error calculating optimal action: {e}")
            return {
                "action": "hold",
                "reason": f"Calculation error: {str(e)}",
                "target_power": 0,
                "target_battery_level": None,
                "profit_forecast": 0,
                "next_opportunity": None
            }

    def _analyze_current_state_from_sensors(self) -> Dict[str, Any]:
        """Analyze current state using only sensor data."""
        battery_level = self.sensor_helper.get_battery_level()
        pv_power = self.sensor_helper.get_pv_power()
        load_power = self.sensor_helper.get_load_power()
        grid_power = self.sensor_helper.get_grid_power()
        
        # Get derived values from sensors
        surplus_power = self.sensor_helper.get_surplus_power()
        net_consumption = self.sensor_helper.get_net_consumption()
        available_battery_wh = self.sensor_helper.get_available_battery_capacity()
        
        # Get configuration from sensors
        battery_capacity = self.sensor_helper.get_battery_capacity()
        min_reserve = self.sensor_helper.get_min_battery_reserve()
        
        # Calculate battery power from grid power (approximation)
        # Positive = charging, negative = discharging
        battery_power = grid_power - surplus_power if surplus_power <= 0 else -surplus_power
        
        return {
            'pv_power': pv_power,
            'load_power': load_power,
            'battery_level': battery_level,
            'battery_power': battery_power,
            'grid_power': grid_power,
            'surplus_power': surplus_power,
            'net_consumption': net_consumption,
            'available_battery_wh': available_battery_wh,
            'battery_capacity': battery_capacity,
            'min_reserve_percent': min_reserve,
            'charging': battery_power > 0,
            'discharging': battery_power < 0,
        }

    def _find_arbitrage_opportunities_from_sensors(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find arbitrage opportunities using sensor data."""
        # Get current prices from sensors
        current_buy_price = self.sensor_helper.get_current_buy_price()
        current_sell_price = self.sensor_helper.get_current_sell_price()
        min_buy_price_24h = self.sensor_helper.get_min_buy_price_24h()
        max_sell_price_24h = self.sensor_helper.get_max_sell_price_24h()
        
        # Get configuration from sensors
        min_margin = self.sensor_helper.get_min_arbitrage_margin()
        battery_efficiency = self.sensor_helper.get_battery_efficiency()
        
        opportunities = []
        
        # Check immediate arbitrage opportunity
        if current_sell_price > current_buy_price:
            roi = self.sensor_helper.get_arbitrage_roi(current_buy_price, current_sell_price)
            
            if roi >= min_margin:
                gross_profit = current_sell_price - current_buy_price
                net_profit = gross_profit * battery_efficiency
                
                opportunities.append({
                    'buy_price': current_buy_price,
                    'sell_price': current_sell_price,
                    'buy_time': datetime.now(timezone.utc).isoformat(),
                    'sell_time': datetime.now(timezone.utc).isoformat(),
                    'roi_percent': roi,
                    'net_profit_per_kwh': net_profit,
                    'degradation_cost': 0.0,  # Simplified for now
                    'cost_per_cycle': 0.0,
                    'depth_of_discharge': 0.0,
                    'equivalent_cycles': 0.0,
                    'is_immediate_buy': True,
                    'is_immediate_sell': True
                })
        
        # Check future arbitrage opportunity (buy low, sell high)
        if max_sell_price_24h > min_buy_price_24h:
            roi = self.sensor_helper.get_arbitrage_roi(min_buy_price_24h, max_sell_price_24h)
            
            if roi >= min_margin:
                gross_profit = max_sell_price_24h - min_buy_price_24h
                net_profit = gross_profit * battery_efficiency
                
                # Determine if we should buy or sell now
                is_immediate_buy = abs(current_buy_price - min_buy_price_24h) < 0.001
                is_immediate_sell = abs(current_sell_price - max_sell_price_24h) < 0.001
                
                opportunities.append({
                    'buy_price': min_buy_price_24h,
                    'sell_price': max_sell_price_24h,
                    'buy_time': (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),  # Approximation
                    'sell_time': (datetime.now(timezone.utc) + timedelta(hours=18)).isoformat(),  # Approximation
                    'roi_percent': roi,
                    'net_profit_per_kwh': net_profit,
                    'degradation_cost': 0.0,  # Simplified for now
                    'cost_per_cycle': 0.0,
                    'depth_of_discharge': 0.0,
                    'equivalent_cycles': 0.0,
                    'is_immediate_buy': is_immediate_buy,
                    'is_immediate_sell': is_immediate_sell
                })
        
        # Sort by ROI
        opportunities.sort(key=lambda x: x['roi_percent'], reverse=True)
        return opportunities


    def _make_decision_from_sensors(
        self, 
        current_state: Dict[str, Any], 
        opportunities: List[Dict[str, Any]], 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make arbitrage decisions using only sensor data."""
        
        # Get configuration from sensors
        max_battery_power = self.sensor_helper.get_max_battery_power()
        min_arbitrage_margin = self.sensor_helper.get_min_arbitrage_margin()
        max_daily_cycles = self.sensor_helper.get_max_daily_cycles()
        
        battery_level = current_state['battery_level']
        surplus_power = current_state['surplus_power']
        available_battery = current_state['available_battery_wh']
        min_reserve = current_state['min_reserve_percent']
        
        best_opportunity = opportunities[0] if opportunities else None
        
        # Check daily cycle limits using sensor data
        cycle_limit_check = self._check_daily_cycle_limits_from_sensors(data, current_state)
        if cycle_limit_check['blocked']:
            return {
                "action": "hold",
                "reason": cycle_limit_check['reason'],
                "target_power": 0,
                "target_battery_level": battery_level,
                "profit_forecast": 0,
                "daily_cycles": cycle_limit_check['daily_cycles']
            }
        
        # Priority 1: Immediate arbitrage sell if profitable and battery available
        if (best_opportunity and best_opportunity.get('is_immediate_sell') and 
            available_battery > 0 and self.sensor_helper.is_battery_discharging_viable()):
            
            discharge_power = min(max_battery_power, available_battery / 2)  # Wh / 2h = W for 2-hour discharge
            return {
                "action": "sell_arbitrage",
                "reason": f"Selling for arbitrage profit: {best_opportunity['roi_percent']:.1f}% ROI",
                "target_power": -discharge_power,
                "target_battery_level": min_reserve + 5,
                "profit_forecast": best_opportunity['net_profit_per_kwh'] * (discharge_power / 1000),  # Convert W to kW for profit calc
                "opportunity": best_opportunity
            }
        
        # Priority 2: Immediate arbitrage buy if profitable and battery has space
        if (best_opportunity and best_opportunity.get('is_immediate_buy') and 
            self.sensor_helper.is_battery_charging_viable()):
            
            charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
            return {
                "action": "charge_arbitrage", 
                "reason": f"Charging for future arbitrage: {best_opportunity['roi_percent']:.1f}% ROI",
                "target_power": charge_power,
                "target_battery_level": 95.0,
                "profit_forecast": best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),  # Convert W to kW for profit calc
                "opportunity": best_opportunity
            }
        
        # Priority 3: Store excess solar power
        if surplus_power > 100:  # 100W threshold
            if battery_level < 95:
                charge_power = min(max_battery_power, surplus_power)
                return {
                    "action": "charge_solar",
                    "reason": "Storing solar energy in battery",
                    "target_power": charge_power,
                    "target_battery_level": min(95, battery_level + 10),
                    "profit_forecast": 0,
                    "opportunity": None
                }
            else:
                export_power = surplus_power
                return {
                    "action": "export_solar",
                    "reason": "Exporting excess solar to grid",
                    "target_power": export_power,
                    "target_battery_level": battery_level,
                    "profit_forecast": 0,
                    "opportunity": None
                }
        
        # Priority 4: Use battery to cover load deficit
        net_consumption = current_state['net_consumption']
        if net_consumption > 100 and available_battery > 500:  # 100W and 500Wh thresholds
            discharge_power = min(max_battery_power, net_consumption, available_battery / 2)  # Wh / 2h = W
            return {
                "action": "discharge_load",
                "reason": "Using battery to cover load",
                "target_power": -discharge_power,
                "target_battery_level": max(min_reserve, battery_level - 5),
                "profit_forecast": 0,
                "opportunity": None
            }
        
        # Default: Hold position
        return {
            "action": "hold",
            "reason": "No beneficial action identified",
            "target_power": 0,
            "target_battery_level": battery_level,
            "profit_forecast": sum([op['net_profit_per_kwh'] for op in opportunities[:3]]),
            "next_opportunity": best_opportunity
        }

    def _is_current_time_window(self, time_string: str, tolerance_minutes: int = 30) -> bool:
        try:
            window_time = datetime.fromisoformat(time_string.replace('Z', '+00:00'))
            current_time = datetime.now(timezone.utc)
            
            time_diff = abs((window_time - current_time).total_seconds() / 60)
            return time_diff <= tolerance_minutes
            
        except Exception:
            return False

    def _get_battery_specs(self, config: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, float]:
        return {
            'capacity': config.get('battery_capacity', 15.0),
            'cost': options.get('battery_cost', config.get('battery_cost', 7500)),
            'cycles': options.get('battery_cycles', config.get('battery_cycles', 6000)),
            'degradation_factor': options.get('degradation_factor', config.get('degradation_factor', 1.0))
        }


    def _check_daily_cycle_limits_from_sensors(self, data: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Check daily cycle limits using sensor data."""
        
        # Get configuration from sensors  
        max_daily_cycles = self.sensor_helper.get_max_daily_cycles()
        battery_level = current_state['battery_level']
        
        # Get cycle data from coordinator data (these come from sensors)
        today_cycles = data.get('today_battery_cycles', 0.0)
        total_cycles = data.get('total_battery_cycles', 0.0)
        
        # Check if daily cycle limit is reached
        if today_cycles >= max_daily_cycles:
            return {
                'blocked': True,
                'reason': f"Daily cycle limit reached: {today_cycles:.2f}/{max_daily_cycles} (from sensor)",
                'daily_cycles': today_cycles,
                'max_cycles': max_daily_cycles,
                'total_cycles': total_cycles
            }
        
        # Check minimum depth for arbitrage (40% minimum battery level)
        min_arbitrage_depth = 40.0  # Fixed at 40% for sensor-based logic
        if battery_level < min_arbitrage_depth:
            return {
                'blocked': True,
                'reason': f"Battery level too low for arbitrage: {battery_level:.1f}% < {min_arbitrage_depth}%",
                'daily_cycles': today_cycles,
                'total_cycles': total_cycles,
                'min_depth_required': min_arbitrage_depth
            }
        
        return {
            'blocked': False,
            'reason': "Cycle limits OK (sensor-based)",
            'daily_cycles': today_cycles,
            'total_cycles': total_cycles,
            'remaining_cycles': max_daily_cycles - today_cycles
        }

