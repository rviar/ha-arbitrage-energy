import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from .sensor_data_helper import SensorDataHelper
from .predictor import EnergyBalancePredictor
from .utils import (
    safe_float, calculate_available_battery_capacity, 
    get_current_price_data, find_price_extremes,
    calculate_arbitrage_profit, calculate_battery_charge_time
)

_LOGGER = logging.getLogger(__name__)

class ArbitrageOptimizer:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.sensor_helper = SensorDataHelper(coordinator.hass, coordinator.entry.entry_id, coordinator)
        self.energy_predictor = EnergyBalancePredictor(self.sensor_helper)

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
        # Negative = charging, positive = discharging
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
            'charging': battery_power < 0,
            'discharging': battery_power > 0,
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
                
                # Calculate detailed profit with degradation
                battery_specs = self._get_battery_specs(
                    self.sensor_helper.coordinator.data.get('config', {}),
                    self.sensor_helper.coordinator.data.get('options', {})
                )
                include_degradation = self.sensor_helper.coordinator.data.get('options', {}).get('include_degradation', 
                                    self.sensor_helper.coordinator.data.get('config', {}).get('include_degradation', True))
                
                # Assume 1kWh transaction for calculation
                energy_amount_wh = 1000  # 1 kWh in Wh
                profit_details = calculate_arbitrage_profit(
                    current_buy_price, current_sell_price, energy_amount_wh,
                    battery_efficiency, battery_specs, include_degradation
                )
                
                opportunities.append({
                    'buy_price': current_buy_price,
                    'sell_price': current_sell_price,
                    'buy_time': datetime.now(timezone.utc).isoformat(),
                    'sell_time': datetime.now(timezone.utc).isoformat(),
                    'roi_percent': profit_details['roi_percent'],
                    'net_profit_per_kwh': profit_details['net_profit'],
                    'degradation_cost': profit_details['degradation_cost'],
                    'cost_per_cycle': profit_details.get('cost_per_cycle', 0.0),
                    'depth_of_discharge': profit_details.get('depth_of_discharge', 0.0),
                    'equivalent_cycles': profit_details.get('equivalent_cycles', 0.0),
                    'is_immediate_buy': True,
                    'is_immediate_sell': True
                })
        
        # Check future arbitrage opportunity (buy low, sell high)
        if max_sell_price_24h > min_buy_price_24h:
            roi = self.sensor_helper.get_arbitrage_roi(min_buy_price_24h, max_sell_price_24h)
            
            if roi >= min_margin:
                # Calculate detailed profit with degradation for future opportunity
                battery_specs = self._get_battery_specs(
                    self.sensor_helper.coordinator.data.get('config', {}),
                    self.sensor_helper.coordinator.data.get('options', {})
                )
                include_degradation = self.sensor_helper.coordinator.data.get('options', {}).get('include_degradation', 
                                    self.sensor_helper.coordinator.data.get('config', {}).get('include_degradation', True))
                
                # Assume 1kWh transaction for calculation
                energy_amount_wh = 1000  # 1 kWh in Wh
                profit_details = calculate_arbitrage_profit(
                    min_buy_price_24h, max_sell_price_24h, energy_amount_wh,
                    battery_efficiency, battery_specs, include_degradation
                )
                
                # Determine if we should buy or sell now
                is_immediate_buy = abs(current_buy_price - min_buy_price_24h) < 0.001
                is_immediate_sell = abs(current_sell_price - max_sell_price_24h) < 0.001
                
                opportunities.append({
                    'buy_price': min_buy_price_24h,
                    'sell_price': max_sell_price_24h,
                    'buy_time': (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),  # Approximation
                    'sell_time': (datetime.now(timezone.utc) + timedelta(hours=18)).isoformat(),  # Approximation
                    'roi_percent': profit_details['roi_percent'],
                    'net_profit_per_kwh': profit_details['net_profit'],
                    'degradation_cost': profit_details['degradation_cost'],
                    'cost_per_cycle': profit_details.get('cost_per_cycle', 0.0),
                    'depth_of_discharge': profit_details.get('depth_of_discharge', 0.0),
                    'equivalent_cycles': profit_details.get('equivalent_cycles', 0.0),
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
        """Make predictive arbitrage decisions using sensor data and energy forecasts."""
        
        # Get configuration from sensors
        max_battery_power = self.sensor_helper.get_max_battery_power()
        min_arbitrage_margin = self.sensor_helper.get_min_arbitrage_margin()
        max_daily_cycles = self.sensor_helper.get_max_daily_cycles()
        
        battery_level = current_state['battery_level']
        surplus_power = current_state['surplus_power']
        available_battery = current_state['available_battery_wh']
        min_reserve = current_state['min_reserve_percent']
        battery_capacity = current_state['battery_capacity']
        
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
        
        # 🧠 PREDICTIVE ANALYSIS - NEW!
        try:
            energy_strategy = self.energy_predictor.assess_battery_strategy(battery_level, battery_capacity)
            energy_situation = self.energy_predictor.get_energy_situation_summary()
            
            _LOGGER.info(f"🔮 Energy forecast: {energy_situation}")
            _LOGGER.info(f"🎯 Strategy recommendation: {energy_strategy['recommendation']} - {energy_strategy['reason']}")
            
        except Exception as e:
            _LOGGER.warning(f"Predictive analysis failed, falling back to basic logic: {e}")
            energy_strategy = {'recommendation': 'hold', 'urgency': 'low'}
            energy_situation = 'unknown'
        
        # 🎯 PREDICTIVE DECISION MAKING
        
        # Strategy-based decisions with price validation
        if energy_strategy['recommendation'] == 'charge_aggressive' and energy_strategy['urgency'] == 'high':
            # High urgency charging - accept lower margins
            if (best_opportunity and best_opportunity.get('is_immediate_buy') and 
                best_opportunity['roi_percent'] >= min_arbitrage_margin * 0.7):  # Accept 70% of normal margin
                
                charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                return {
                    "action": "charge_arbitrage",
                    "reason": f"⚡ PREDICTIVE: {energy_strategy['reason']} (ROI: {best_opportunity['roi_percent']:.1f}%)",
                    "target_power": charge_power,
                    "target_battery_level": energy_strategy['target_battery_level'],
                    "profit_forecast": best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),
                    "opportunity": best_opportunity,
                    "strategy": energy_strategy['recommendation']
                }
        
        elif energy_strategy['recommendation'] == 'charge_moderate':
            # Moderate charging - normal margins  
            if (best_opportunity and best_opportunity.get('is_immediate_buy') and 
                best_opportunity['roi_percent'] >= min_arbitrage_margin):
                
                charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                return {
                    "action": "charge_arbitrage",
                    "reason": f"📊 PREDICTIVE: {energy_strategy['reason']} (ROI: {best_opportunity['roi_percent']:.1f}%)",
                    "target_power": charge_power,
                    "target_battery_level": energy_strategy['target_battery_level'],
                    "profit_forecast": best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),
                    "opportunity": best_opportunity,
                    "strategy": energy_strategy['recommendation']
                }
        
        elif energy_strategy['recommendation'] in ['sell_aggressive', 'sell_partial']:
            # Strategic selling
            if (best_opportunity and best_opportunity.get('is_immediate_sell') and 
                available_battery > 0 and self.sensor_helper.is_battery_discharging_viable()):
                
                # Respect strategy target level
                max_discharge_wh = (battery_level - energy_strategy['target_battery_level']) / 100 * battery_capacity
                max_discharge_wh = max(0, max_discharge_wh)
                
                if max_discharge_wh > 1000:  # At least 1kWh to sell
                    discharge_power = min(max_battery_power, max_discharge_wh / 2)  # 2-hour discharge
                    
                    return {
                        "action": "sell_arbitrage",
                        "reason": f"💰 PREDICTIVE: {energy_strategy['reason']} (ROI: {best_opportunity['roi_percent']:.1f}%)",
                        "target_power": -discharge_power,
                        "target_battery_level": energy_strategy['target_battery_level'],
                        "profit_forecast": best_opportunity['net_profit_per_kwh'] * (discharge_power / 1000),
                        "opportunity": best_opportunity,
                        "strategy": energy_strategy['recommendation']
                    }
        
        # 📈 FALLBACK: Traditional arbitrage if no predictive action
        # Priority 1: Immediate arbitrage sell if very profitable
        if (best_opportunity and best_opportunity.get('is_immediate_sell') and 
            available_battery > 0 and self.sensor_helper.is_battery_discharging_viable() and
            best_opportunity['roi_percent'] >= min_arbitrage_margin * 1.5):  # Higher threshold for fallback
            
            discharge_power = min(max_battery_power, available_battery / 2)
            return {
                "action": "sell_arbitrage",
                "reason": f"💸 TRADITIONAL: High ROI opportunity: {best_opportunity['roi_percent']:.1f}%",
                "target_power": -discharge_power,
                "target_battery_level": min_reserve + 5,
                "profit_forecast": best_opportunity['net_profit_per_kwh'] * (discharge_power / 1000),
                "opportunity": best_opportunity,
                "strategy": "traditional"
            }
        
        # Priority 2: Immediate arbitrage buy if very profitable
        if (best_opportunity and best_opportunity.get('is_immediate_buy') and 
            self.sensor_helper.is_battery_charging_viable() and
            best_opportunity['roi_percent'] >= min_arbitrage_margin * 1.5):  # Higher threshold for fallback
            
            charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
            return {
                "action": "charge_arbitrage", 
                "reason": f"⚡ TRADITIONAL: High ROI opportunity: {best_opportunity['roi_percent']:.1f}%",
                "target_power": charge_power,
                "target_battery_level": 95.0,
                "profit_forecast": best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),
                "opportunity": best_opportunity,
                "strategy": "traditional"
            }
        # Default: Hold position with predictive insight
        hold_reason = "🔄 PREDICTIVE HOLD: " + energy_strategy.get('reason', 'No beneficial action identified')
        
        return {
            "action": "hold",
            "reason": hold_reason,
            "target_power": 0,
            "target_battery_level": battery_level,
            "profit_forecast": sum([op['net_profit_per_kwh'] for op in opportunities[:3]]),
            "next_opportunity": best_opportunity,
            "energy_situation": energy_situation,
            "strategy": energy_strategy['recommendation'],
            "confidence": energy_strategy.get('confidence', 0.5)
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
        # Get coordinator data for static config parameters
        coordinator_config = self.sensor_helper.coordinator.data.get('config', {})
        coordinator_options = self.sensor_helper.coordinator.data.get('options', {})
        
        return {
            'capacity': self.sensor_helper.get_battery_capacity(),  # Get current capacity from coordinator via sensor_helper
            'cost': coordinator_options.get('battery_cost', coordinator_config.get('battery_cost', 7500)),
            'cycles': coordinator_options.get('battery_cycles', coordinator_config.get('battery_cycles', 6000)),
            'degradation_factor': coordinator_options.get('degradation_factor', coordinator_config.get('degradation_factor', 1.0))
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
        
        # Check minimum depth for arbitrage (configurable minimum battery level)
        min_arbitrage_depth = self.sensor_helper.get_min_arbitrage_depth()
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

