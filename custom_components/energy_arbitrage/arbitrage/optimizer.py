import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from .utils import (
    safe_float, calculate_available_battery_capacity, 
    get_current_price_data, find_price_extremes,
    calculate_arbitrage_profit, calculate_battery_charge_time
)

_LOGGER = logging.getLogger(__name__)

class ArbitrageOptimizer:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def calculate_optimal_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            current_state = self._analyze_current_state(data)
            arbitrage_opportunities = self._find_arbitrage_opportunities(data)
            
            decision = self._make_decision(current_state, arbitrage_opportunities, data)
            
            _LOGGER.info(
                f"Arbitrage decision: {decision['action']} - {decision['reason']}"
                f" (Battery: {current_state['battery_level']:.1f}%, "
                f"Solar: {current_state['pv_power']:.1f}kW, "
                f"Load: {current_state['load_power']:.1f}kW)"
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

    def _analyze_current_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        config = data.get('config', {})
        
        pv_power = data.get('pv_power', 0)
        load_power = data.get('load_power', 0)
        battery_level = data.get('battery_level', 0)
        battery_power = data.get('battery_power', 0)
        grid_power = data.get('grid_power', 0)
        
        battery_capacity = config.get('battery_capacity', 15.0)
        min_reserve = config.get('min_battery_reserve', 20)
        
        surplus_power = pv_power - load_power
        available_battery = calculate_available_battery_capacity(
            battery_level, min_reserve, battery_capacity
        )
        
        return {
            'pv_power': pv_power,
            'load_power': load_power,
            'battery_level': battery_level,
            'battery_power': battery_power,
            'grid_power': grid_power,
            'surplus_power': surplus_power,
            'available_battery_kwh': available_battery,
            'battery_capacity': battery_capacity,
            'min_reserve_percent': min_reserve,
            'charging': battery_power > 0,
            'discharging': battery_power < 0,
        }

    def _find_arbitrage_opportunities(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        price_data = data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        sell_prices = price_data.get('sell_prices', [])
        
        if not buy_prices or not sell_prices:
            return []
        
        config = data.get('config', {})
        options = data.get('options', {})
        
        planning_horizon = config.get('planning_horizon', 24)
        min_margin = options.get('min_arbitrage_margin', config.get('min_arbitrage_margin', 5))
        battery_efficiency = config.get('battery_efficiency', 90) / 100.0
        
        opportunities = []
        
        current_time = datetime.now(timezone.utc)
        current_buy_price_data = get_current_price_data(buy_prices, current_time)
        current_sell_price_data = get_current_price_data(sell_prices, current_time)
        
        if not current_buy_price_data or not current_sell_price_data:
            return []
        
        current_buy_price = current_buy_price_data.get('value', 0)
        current_sell_price = current_sell_price_data.get('value', 0)
        
        high_price_windows = find_price_extremes(sell_prices, planning_horizon, 'peaks')
        low_price_windows = find_price_extremes(buy_prices, planning_horizon, 'valleys')
        
        for high_window in high_price_windows:
            high_price = high_window.get('value', 0)
            high_start = high_window.get('start', '')
            
            for low_window in low_price_windows:
                low_price = low_window.get('value', 0)
                low_start = low_window.get('start', '')
                
                battery_specs = self._get_battery_specs(config, options)
                include_degradation = options.get('include_degradation', config.get('include_degradation', True))
                
                profit_calc = calculate_arbitrage_profit(
                    low_price, high_price, 1.0, battery_efficiency,
                    battery_specs, include_degradation
                )
                
                if profit_calc['roi_percent'] >= min_margin:
                    opportunities.append({
                        'buy_price': low_price,
                        'sell_price': high_price,
                        'buy_time': low_start,
                        'sell_time': high_start,
                        'roi_percent': profit_calc['roi_percent'],
                        'net_profit_per_kwh': profit_calc['net_profit'],
                        'degradation_cost': profit_calc['degradation_cost'],
                        'cost_per_cycle': profit_calc.get('cost_per_cycle', 0.0),
                        'depth_of_discharge': profit_calc.get('depth_of_discharge', 0.0),
                        'equivalent_cycles': profit_calc.get('equivalent_cycles', 0.0),
                        'is_immediate_buy': self._is_current_time_window(low_start),
                        'is_immediate_sell': self._is_current_time_window(high_start)
                    })
        
        if current_sell_price > current_buy_price:
            battery_specs = self._get_battery_specs(config, options)
            include_degradation = options.get('include_degradation', config.get('include_degradation', True))
            
            immediate_profit = calculate_arbitrage_profit(
                current_buy_price, current_sell_price, 1.0, battery_efficiency,
                battery_specs, include_degradation
            )
            
            if immediate_profit['roi_percent'] >= min_margin:
                opportunities.append({
                    'buy_price': current_buy_price,
                    'sell_price': current_sell_price,
                    'buy_time': current_buy_price_data.get('start', ''),
                    'sell_time': current_sell_price_data.get('start', ''),
                    'roi_percent': immediate_profit['roi_percent'],
                    'net_profit_per_kwh': immediate_profit['net_profit'],
                    'degradation_cost': immediate_profit['degradation_cost'],
                    'cost_per_cycle': immediate_profit.get('cost_per_cycle', 0.0),
                    'depth_of_discharge': immediate_profit.get('depth_of_discharge', 0.0),
                    'equivalent_cycles': immediate_profit.get('equivalent_cycles', 0.0),
                    'is_immediate_buy': True,
                    'is_immediate_sell': True
                })
        
        opportunities.sort(key=lambda x: x['roi_percent'], reverse=True)
        return opportunities

    def _make_decision(
        self, 
        current_state: Dict[str, Any], 
        opportunities: List[Dict[str, Any]], 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        config = data.get('config', {})
        options = data.get('options', {})
        
        max_battery_power = config.get('max_battery_power', 5.0)
        self_consumption_priority = options.get(
            'self_consumption_priority', 
            config.get('self_consumption_priority', True)
        )
        
        battery_level = current_state['battery_level']
        surplus_power = current_state['surplus_power']
        available_battery = current_state['available_battery_kwh']
        battery_capacity = current_state['battery_capacity']
        min_reserve = current_state['min_reserve_percent']
        
        best_opportunity = opportunities[0] if opportunities else None
        
        cycle_limit_check = self._check_daily_cycle_limits(data, current_state)
        if cycle_limit_check['blocked']:
            return {
                "action": "hold",
                "reason": cycle_limit_check['reason'],
                "target_power": 0,
                "target_battery_level": battery_level,
                "profit_forecast": 0,
                "daily_cycles": cycle_limit_check['daily_cycles']
            }
        
        if best_opportunity and best_opportunity.get('is_immediate_sell') and available_battery > 0:
            if battery_level > min_reserve + 10:
                discharge_power = min(max_battery_power, available_battery * 2)
                return {
                    "action": "sell_arbitrage",
                    "reason": f"Selling for arbitrage profit: {best_opportunity['roi_percent']:.1f}% ROI",
                    "target_power": -discharge_power,
                    "target_battery_level": min_reserve + 5,
                    "profit_forecast": best_opportunity['net_profit_per_kwh'] * discharge_power,
                    "opportunity": best_opportunity
                }
        
        if best_opportunity and best_opportunity.get('is_immediate_buy'):
            max_charge_level = 95.0
            if battery_level < max_charge_level:
                charge_power = min(max_battery_power, surplus_power if surplus_power > 0 else max_battery_power)
                return {
                    "action": "charge_arbitrage", 
                    "reason": f"Charging for future arbitrage: {best_opportunity['roi_percent']:.1f}% ROI",
                    "target_power": charge_power,
                    "target_battery_level": max_charge_level,
                    "profit_forecast": best_opportunity['net_profit_per_kwh'] * charge_power,
                    "opportunity": best_opportunity
                }
        
        if surplus_power > 0.1:
            if self_consumption_priority and battery_level < 95:
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
        
        if surplus_power < -0.1 and available_battery > 0.5:
            needed_power = abs(surplus_power)
            discharge_power = min(max_battery_power, needed_power, available_battery * 2)
            return {
                "action": "discharge_load",
                "reason": "Using battery to cover load",
                "target_power": -discharge_power,
                "target_battery_level": max(min_reserve, battery_level - 5),
                "profit_forecast": 0,
                "opportunity": None
            }
        
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

    def _check_daily_cycle_limits(self, data: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
        config = data.get('config', {})
        options = data.get('options', {})
        
        max_daily_cycles = options.get('max_daily_cycles', config.get('max_daily_cycles', 2.0))
        min_arbitrage_depth = options.get('min_arbitrage_depth', config.get('min_arbitrage_depth', 40))
        battery_level = current_state['battery_level']
        
        today_cycles = data.get('today_battery_cycles', 0.0)
        total_cycles = data.get('total_battery_cycles', 0.0)
        
        if today_cycles >= max_daily_cycles:
            return {
                'blocked': True,
                'reason': f"Daily cycle limit reached: {today_cycles:.2f}/{max_daily_cycles} (from inverter)",
                'daily_cycles': today_cycles,
                'max_cycles': max_daily_cycles,
                'total_cycles': total_cycles
            }
        
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
            'reason': "Cycle limits OK",
            'daily_cycles': today_cycles,
            'total_cycles': total_cycles,
            'remaining_cycles': max_daily_cycles - today_cycles
        }

