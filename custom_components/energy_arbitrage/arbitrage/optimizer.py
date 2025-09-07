import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from .sensor_data_helper import SensorDataHelper
from .predictor import EnergyBalancePredictor
from .time_analyzer import TimeWindowAnalyzer
from .strategic_planner import StrategicPlanner
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
        self.time_analyzer = TimeWindowAnalyzer(self.sensor_helper)
        self.strategic_planner = StrategicPlanner(self.sensor_helper, self.energy_predictor, self.time_analyzer)
        self._last_plan_update = None

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
            # Return safe defaults instead of None
            try:
                battery_level = self.sensor_helper.get_battery_level() or 50.0
            except Exception:
                battery_level = 50.0
            return {
                "action": "hold",
                "reason": f"Calculation error: {str(e)}",
                "target_power": 0,
                "target_battery_level": battery_level,  # Use current level instead of None
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
        # Calculate derived values directly
        surplus_power = max(0, pv_power - load_power)  # Positive when PV > Load
        net_consumption = load_power - pv_power        # Net consumption after PV
        available_battery_wh = calculate_available_battery_capacity(battery_level, battery_capacity, min_reserve)
        
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
        # Get price extremes from MQTT data (will be replaced by price_windows analysis)
        price_data = data.get("price_data", {})
        buy_prices = price_data.get("buy_prices", [])
        sell_prices = price_data.get("sell_prices", [])
        
        # Find current extremes (fallback for traditional arbitrage)
        min_buy_price_24h = min([p.get('value', float('inf')) for p in buy_prices[:24]], default=0.0)  # 'value'
        max_sell_price_24h = max([p.get('value', 0) for p in sell_prices[:24]], default=0.0)        # 'value'
        
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
        battery_capacity = current_state['battery_capacity']
        min_reserve = current_state['min_reserve_percent']
        
        # Calculate derived values directly  
        pv_power = current_state['pv_power']
        load_power = current_state['load_power']
        surplus_power = max(0, pv_power - load_power)  # Positive when PV > Load
        available_battery = calculate_available_battery_capacity(battery_level, battery_capacity, min_reserve)
        
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
            energy_strategy = {'recommendation': 'hold', 'urgency': 'low', 'target_battery_level': battery_level}
            energy_situation = 'unknown'
        
        # 🕐 TIME WINDOW ANALYSIS - NEW!
        try:
            price_windows = self.time_analyzer.analyze_price_windows(data.get("price_data", {}), 24)
            price_situation = self.time_analyzer.get_current_price_situation(price_windows)
            
            _LOGGER.info(f"⏰ Price windows found: {len(price_windows)} opportunities")
            _LOGGER.info(f"⚡ Current situation: {price_situation.get('time_pressure', 'low')} time pressure")
            
        except Exception as e:
            _LOGGER.warning(f"Time window analysis failed: {e}")
            price_windows = []
            price_situation = {'time_pressure': 'low', 'current_opportunities': 0}
        
        # 🎯 STRATEGIC PLANNING - NEW! 
        try:
            # Update strategic plan every 30 minutes or when conditions change significantly
            now = datetime.now(timezone.utc)
            should_update_plan = (
                self._last_plan_update is None or
                (now - self._last_plan_update).total_seconds() > 1800 or  # 30 minutes
                price_situation.get('time_pressure') == 'high'  # Urgent situations need fresh plans
            )
            
            if should_update_plan:
                strategic_plan = self.strategic_planner.create_comprehensive_plan(
                    battery_level, battery_capacity, max_battery_power, data.get("price_data", {}), 48
                )
                self._last_plan_update = now
                _LOGGER.info(f"🎯 Strategic plan updated: {strategic_plan.scenario} ({len(strategic_plan.operations)} operations)")
            
            # Get current strategic recommendation
            strategic_recommendation = self.strategic_planner.get_current_recommendation()
            
            _LOGGER.info(f"🧭 Strategic status: {strategic_recommendation.get('plan_status', 'unknown')}")
            _LOGGER.info(f"🎲 Strategic action: {strategic_recommendation.get('action', 'unknown')} - {strategic_recommendation.get('reason', 'No reason')}")
            
        except Exception as e:
            _LOGGER.warning(f"Strategic planning failed: {e}")
            strategic_recommendation = {
                "action": "hold",
                "reason": "Strategic planning unavailable",
                "confidence": 0.3,
                "plan_status": "error"
            }
        
        # 🎯 STRATEGIC DECISION MAKING (HIGHEST PRIORITY)
        
        # Strategic planner takes precedence if it has high-confidence recommendations
        if (strategic_recommendation.get('confidence', 0) >= 0.8 and 
            strategic_recommendation.get('plan_status') in ['executing', 'waiting'] and
            strategic_recommendation.get('action') != 'hold'):
            
            if strategic_recommendation['action'] == 'charge_arbitrage':
                return {
                    "action": "charge_arbitrage",
                    "reason": strategic_recommendation['reason'],
                    "target_power": strategic_recommendation.get('target_power', max_battery_power * 0.8),
                    "target_battery_level": min(95, battery_level + 20),
                    "profit_forecast": 0,  # Will be calculated by strategic planner
                    "opportunity": {"strategic": True, "priority": strategic_recommendation.get('priority', 1)},
                    "strategy": "strategic_plan",
                    "plan_status": strategic_recommendation.get('plan_status'),
                    "confidence": strategic_recommendation.get('confidence', 0.8)
                }
                
            elif strategic_recommendation['action'] == 'sell_arbitrage':
                return {
                    "action": "sell_arbitrage",
                    "reason": strategic_recommendation['reason'],
                    "target_power": strategic_recommendation.get('target_power', -max_battery_power * 0.8),
                    "target_battery_level": max(min_reserve, battery_level - 15),
                    "profit_forecast": 0,  # Will be calculated by strategic planner
                    "opportunity": {"strategic": True, "priority": strategic_recommendation.get('priority', 1)},
                    "strategy": "strategic_plan",
                    "plan_status": strategic_recommendation.get('plan_status'),
                    "confidence": strategic_recommendation.get('confidence', 0.8)
                }
        
        # 🎯 TIME-AWARE PREDICTIVE DECISION MAKING (FALLBACK)
        
        # Check for immediate time-sensitive opportunities
        if price_situation.get('time_pressure') == 'high' and price_situation.get('immediate_action'):
            immediate = price_situation['immediate_action']
            
            if immediate['action'] == 'buy' and self.sensor_helper.is_battery_charging_viable():
                # Immediate buy opportunity ending soon
                if best_opportunity and best_opportunity.get('is_immediate_buy'):
                    charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                    return {
                        "action": "charge_arbitrage",
                        "reason": f"⏰ TIME CRITICAL: Buy window ending in {immediate['time_remaining']:.1f}h (Price: {immediate['price']:.3f})",
                        "target_power": charge_power,
                        "target_battery_level": min(95, battery_level + 20),
                        "profit_forecast": best_opportunity.get('net_profit_per_kwh', 0) * (charge_power / 1000),
                        "opportunity": best_opportunity,
                        "strategy": "time_critical"
                    }
                    
            elif immediate['action'] == 'sell' and available_battery > 1000:
                # Immediate sell opportunity ending soon
                if best_opportunity and best_opportunity.get('is_immediate_sell'):
                    discharge_power = min(max_battery_power, available_battery / immediate['time_remaining'])
                    return {
                        "action": "sell_arbitrage", 
                        "reason": f"⏰ TIME CRITICAL: Sell window ending in {immediate['time_remaining']:.1f}h (Price: {immediate['price']:.3f})",
                        "target_power": -discharge_power,
                        "target_battery_level": max(min_reserve, battery_level - 15),
                        "profit_forecast": best_opportunity.get('net_profit_per_kwh', 0) * (discharge_power / 1000),
                        "opportunity": best_opportunity,
                        "strategy": "time_critical"
                    }
        
        # Strategy-based decisions with time window validation
        if energy_strategy['recommendation'] == 'charge_aggressive' and energy_strategy['urgency'] == 'high':
            # High urgency charging - plan operation if time allows
            if best_opportunity and best_opportunity.get('is_immediate_buy'):
                
                # Check if we have enough time to charge what we need
                target_energy = (energy_strategy['target_battery_level'] - battery_level) / 100 * battery_capacity
                planned_operation = self.time_analyzer.plan_battery_operation(
                    target_energy, 'charge', price_windows, max_battery_power
                )
                
                if planned_operation and planned_operation.feasible:
                    # We can complete the planned operation
                    return {
                        "action": "charge_arbitrage",
                        "reason": f"⚡ PLANNED: {energy_strategy['reason']} (Time: {planned_operation.duration_hours:.1f}h, ROI: {best_opportunity['roi_percent']:.1f}%)",
                        "target_power": planned_operation.target_power_w,
                        "target_battery_level": energy_strategy['target_battery_level'],
                        "profit_forecast": best_opportunity['net_profit_per_kwh'] * (planned_operation.target_power_w / 1000),
                        "opportunity": best_opportunity,
                        "strategy": f"{energy_strategy['recommendation']}_planned",
                        "completion_time": planned_operation.completion_time.isoformat()
                    }
                elif best_opportunity['roi_percent'] >= min_arbitrage_margin * 0.7:
                    # Fallback to immediate charging with reduced margin
                    charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                    return {
                        "action": "charge_arbitrage",
                        "reason": f"⚡ IMMEDIATE: Limited time, charge now (ROI: {best_opportunity['roi_percent']:.1f}%)",
                        "target_power": charge_power,
                        "target_battery_level": min(95, battery_level + 15),  # Conservative target
                        "profit_forecast": best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),
                        "opportunity": best_opportunity,
                        "strategy": f"{energy_strategy['recommendation']}_immediate"
                    }
        
        elif energy_strategy['recommendation'] == 'charge_moderate':
            # Moderate charging with time planning
            if best_opportunity and best_opportunity.get('is_immediate_buy') and best_opportunity['roi_percent'] >= min_arbitrage_margin:
                
                # Plan the operation if time permits
                target_energy = (energy_strategy['target_battery_level'] - battery_level) / 100 * battery_capacity
                planned_operation = self.time_analyzer.plan_battery_operation(
                    target_energy, 'charge', price_windows, max_battery_power
                )
                
                if planned_operation and planned_operation.feasible:
                    return {
                        "action": "charge_arbitrage",
                        "reason": f"📊 PLANNED: {energy_strategy['reason']} (Time: {planned_operation.duration_hours:.1f}h, ROI: {best_opportunity['roi_percent']:.1f}%)",
                        "target_power": planned_operation.target_power_w,
                        "target_battery_level": energy_strategy['target_battery_level'],
                        "profit_forecast": best_opportunity['net_profit_per_kwh'] * (planned_operation.target_power_w / 1000),
                        "opportunity": best_opportunity,
                        "strategy": f"{energy_strategy['recommendation']}_planned",
                        "completion_time": planned_operation.completion_time.isoformat()
                    }
                else:
                    # Standard charging if planning fails
                    charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                    return {
                        "action": "charge_arbitrage",
                        "reason": f"📊 STANDARD: {energy_strategy['reason']} (ROI: {best_opportunity['roi_percent']:.1f}%)",
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
        # Default: Hold position with strategic insight
        strategic_info = ""
        if strategic_recommendation.get('plan_status') == 'waiting':
            strategic_info = f" Strategic: {strategic_recommendation.get('reason', 'Planning')}"
        elif price_situation.get('next_opportunity'):
            next_opp = price_situation['next_opportunity']
            strategic_info = f" Next: {next_opp['action']} in {next_opp['time_until_start']:.1f}h"
        
        # Choose the most informative hold reason
        if strategic_recommendation.get('confidence', 0) > energy_strategy.get('confidence', 0):
            hold_reason = f"🎯 STRATEGIC HOLD: {strategic_recommendation.get('reason', 'No strategic action')}{strategic_info}"
            primary_confidence = strategic_recommendation.get('confidence', 0.5)
            primary_strategy = "strategic"
        else:
            hold_reason = f"🔄 PREDICTIVE HOLD: {energy_strategy.get('reason', 'No beneficial action identified')}{strategic_info}"
            primary_confidence = energy_strategy.get('confidence', 0.5)
            primary_strategy = energy_strategy['recommendation']
        
        return {
            "action": "hold",
            "reason": hold_reason,
            "target_power": 0,
            "target_battery_level": battery_level,
            "profit_forecast": sum([op['net_profit_per_kwh'] for op in opportunities[:3]]),
            "next_opportunity": best_opportunity,
            "energy_situation": energy_situation,
            "strategy": primary_strategy,
            "confidence": primary_confidence,
            "time_pressure": price_situation.get('time_pressure', 'low'),
            "price_windows_count": len(price_windows),
            "next_window": price_situation.get('next_opportunity'),
            "strategic_status": strategic_recommendation.get('plan_status', 'no_plan'),
            "strategic_confidence": strategic_recommendation.get('confidence', 0)
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

