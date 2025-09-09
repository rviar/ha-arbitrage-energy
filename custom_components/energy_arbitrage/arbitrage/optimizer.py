import logging
from datetime import datetime, timedelta
from .utils import get_current_ha_time, get_ha_timezone, parse_datetime
from typing import Dict, Any, List
from ..const import CONF_CURRENCY, DEFAULT_CURRENCY

from .sensor_data_helper import SensorDataHelper
from .exceptions import safe_execute, OptimizationError, log_performance
from .predictor import EnergyBalancePredictor
from .time_analyzer import TimeWindowAnalyzer
from .strategic_planner import StrategicPlanner
from .decision_handlers import (
    DecisionContext, DecisionResult,
    StrategicDecisionHandler, TimeCriticalDecisionHandler, 
    PredictiveDecisionHandler, TraditionalArbitrageHandler, HoldDecisionHandler
)
from .constants import (
    STRATEGIC_PLAN_UPDATE_INTERVAL, PRICE_ANALYSIS_24H_WINDOW,
    ENERGY_CALCULATION_1KWH, PRICE_COMPARISON_TOLERANCE,
    FUTURE_BUY_TIME_OFFSET, FUTURE_SELL_TIME_OFFSET,
    DEFAULT_BATTERY_COST, DEFAULT_BATTERY_CYCLES, DEFAULT_DEGRADATION_FACTOR,
    TIME_WINDOW_TOLERANCE_MINUTES, FALLBACK_BATTERY_LEVEL_PERCENT,
    FALLBACK_CONFIDENCE_LEVEL
)
from .utils import (
    calculate_available_battery_capacity, 
    calculate_arbitrage_profit
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
        
        # Initialize decision handlers in priority order
        self.decision_handlers = [
            StrategicDecisionHandler(self.sensor_helper, self.time_analyzer),
            TimeCriticalDecisionHandler(self.sensor_helper, self.time_analyzer),  
            PredictiveDecisionHandler(self.sensor_helper, self.time_analyzer),
            TraditionalArbitrageHandler(self.sensor_helper, self.time_analyzer),
            HoldDecisionHandler(self.sensor_helper, self.time_analyzer)
        ]

    @safe_execute(default_return={
        "action": "hold",
        "reason": "Calculation error - using safe defaults",
        "target_power": 0,
        "target_battery_level": FALLBACK_BATTERY_LEVEL_PERCENT,
        "profit_forecast": 0,
        "next_opportunity": None
    })
    @log_performance
    async def calculate_optimal_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
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

    @safe_execute(default_return={
        'pv_power': 0, 'load_power': 0, 'battery_level': FALLBACK_BATTERY_LEVEL_PERCENT,
        'battery_power': 0, 'grid_power': 0, 'surplus_power': 0, 'net_consumption': 0,
        'available_battery_wh': 0, 'battery_capacity': 10000, 'min_reserve_percent': 20,
        'charging': False, 'discharging': False
    })
    def _analyze_current_state_from_sensors(self) -> Dict[str, Any]:
        """Analyze current state using only sensor data."""
        battery_level = self.sensor_helper.get_battery_level()
        pv_power = self.sensor_helper.get_pv_power()
        load_power = self.sensor_helper.get_load_power()
        grid_power = self.sensor_helper.get_grid_power()
        
        # Get configuration from sensors FIRST
        battery_capacity = self.sensor_helper.get_battery_capacity()
        min_reserve = self.sensor_helper.get_min_battery_reserve()
        
        # Calculate derived values using configuration
        surplus_power = max(0, pv_power - load_power)  # Positive when PV > Load
        net_consumption = load_power - pv_power        # Net consumption after PV
        available_battery_wh = calculate_available_battery_capacity(battery_level, battery_capacity, min_reserve)
        
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

    @safe_execute(default_return=[])
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
        min_buy_price_24h = min([p.get('value', float('inf')) for p in buy_prices[:PRICE_ANALYSIS_24H_WINDOW]], default=0.0)  # 'value'
        max_sell_price_24h = max([p.get('value', 0) for p in sell_prices[:PRICE_ANALYSIS_24H_WINDOW]], default=0.0)        # 'value'
        
        # Get configuration from sensors
        min_margin = self.sensor_helper.get_min_arbitrage_margin()
        battery_efficiency = self.sensor_helper.get_battery_efficiency()
        
        opportunities = []
        
        # Check immediate arbitrage opportunity
        if current_sell_price > current_buy_price:
            roi = self.sensor_helper.get_arbitrage_roi(current_buy_price, current_sell_price)
            
            if roi >= min_margin:
                # profit calculation done in profit_details below
                
                # Calculate detailed profit with degradation
                battery_specs = self._get_battery_specs(
                    self.sensor_helper.coordinator.data.get('config', {}),
                    self.sensor_helper.coordinator.data.get('options', {})
                )
                include_degradation = self.sensor_helper.coordinator.data.get('options', {}).get('include_degradation', 
                                    self.sensor_helper.coordinator.data.get('config', {}).get('include_degradation', True))
                
                # Assume 1kWh transaction for calculation
                energy_amount_wh = ENERGY_CALCULATION_1KWH  # 1 kWh in Wh
                profit_details = calculate_arbitrage_profit(
                    current_buy_price, current_sell_price, energy_amount_wh,
                    battery_efficiency, battery_specs, include_degradation
                )
                
                opportunities.append({
                    'buy_price': current_buy_price,
                    'sell_price': current_sell_price,
                    # FIXED: Use HA timezone for arbitrage timestamps
                    'buy_time': get_current_ha_time().isoformat(),
                    'sell_time': get_current_ha_time().isoformat(),
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
                energy_amount_wh = ENERGY_CALCULATION_1KWH  # 1 kWh in Wh
                profit_details = calculate_arbitrage_profit(
                    min_buy_price_24h, max_sell_price_24h, energy_amount_wh,
                    battery_efficiency, battery_specs, include_degradation
                )
                
                # Determine if we should buy or sell now
                is_immediate_buy = abs(current_buy_price - min_buy_price_24h) < PRICE_COMPARISON_TOLERANCE
                is_immediate_sell = abs(current_sell_price - max_sell_price_24h) < PRICE_COMPARISON_TOLERANCE
                
                # FIXED: Use HA timezone for arbitrage timestamps
                ha_now = get_current_ha_time()
                opportunities.append({
                    'buy_price': min_buy_price_24h,
                    'sell_price': max_sell_price_24h,
                    'buy_time': (ha_now + timedelta(hours=FUTURE_BUY_TIME_OFFSET)).isoformat(),  # Approximation
                    'sell_time': (ha_now + timedelta(hours=FUTURE_SELL_TIME_OFFSET)).isoformat(),  # Approximation
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
        
        # Check daily cycle limits first
        cycle_limit_check = self._check_daily_cycle_limits_from_sensors(data, current_state)
        if cycle_limit_check['blocked']:
            return {
                "action": "hold",
                "reason": cycle_limit_check['reason'],
                "target_power": 0,
                "target_battery_level": current_state['battery_level'],
                "profit_forecast": 0,
                "daily_cycles": cycle_limit_check['daily_cycles']
            }
        
        # Gather analysis data
        analysis_data = self._gather_analysis_data(current_state, data)
        
        # Calculate available battery capacity for context
        available_battery_capacity = calculate_available_battery_capacity(
            current_state['battery_level'], 
            current_state['battery_capacity'], 
            current_state['min_reserve_percent']
        )
        current_state['available_battery_capacity'] = available_battery_capacity
        
        # Add analysis data to the data dict for handlers to access
        data_with_analysis = dict(data)
        data_with_analysis['analysis'] = analysis_data
        
        # Create decision context
        context = DecisionContext(
            current_state=current_state,
            opportunities=opportunities,
            data=data_with_analysis,
            max_battery_power=self.sensor_helper.get_max_battery_power(),
            min_arbitrage_margin=self.sensor_helper.get_min_arbitrage_margin(),
            energy_strategy=analysis_data['energy_strategy'],
            price_situation=analysis_data['price_situation'], 
            strategic_recommendation=analysis_data['strategic_recommendation']
        )
        
        # Process through decision handlers in priority order
        for handler in self.decision_handlers:
            if handler.can_handle(context):
                _LOGGER.debug(f"Using {handler.__class__.__name__} for decision")
                decision = handler.make_decision(context)
                if decision:
                    return self._convert_decision_to_dict(decision)
        
        # Fallback - should never reach here due to HoldDecisionHandler
        return {
            "action": "hold",
            "reason": "🔄 FALLBACK: No decision handler available",
            "target_power": 0,
            "target_battery_level": current_state['battery_level'],
            "profit_forecast": 0,
            "strategy": "fallback"
        }

    def _gather_analysis_data(self, current_state: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Gather all analysis data needed for decision making."""
        
        # 🧠 PREDICTIVE ANALYSIS
        try:
            energy_strategy = self.energy_predictor.assess_battery_strategy(
                current_state['battery_level'], current_state['battery_capacity']
            )
            energy_situation = self.energy_predictor.get_energy_situation_summary()
            
            _LOGGER.info(f"🔮 Energy forecast: {energy_situation}")
            _LOGGER.info(f"🎯 Strategy recommendation: {energy_strategy['recommendation']} - {energy_strategy['reason']}")
            
        except Exception as e:
            _LOGGER.warning(f"Predictive analysis failed, falling back to basic logic: {e}")
            energy_strategy = {
                'recommendation': 'hold', 
                'urgency': 'low', 
                'target_battery_level': current_state['battery_level']
            }
            energy_situation = 'unknown'
        
        # 🕐 TIME WINDOW ANALYSIS  
        try:
            price_windows = self.time_analyzer.analyze_price_windows(data.get("price_data", {}), PRICE_ANALYSIS_24H_WINDOW)
            price_situation = self.time_analyzer.get_current_price_situation(price_windows)
            
            _LOGGER.info(f"⏰ Price windows found: {len(price_windows)} opportunities")
            _LOGGER.info(f"⚡ Current situation: {price_situation.get('time_pressure', 'low')} time pressure")
            
        except Exception as e:
            _LOGGER.warning(f"Time window analysis failed: {e}")
            price_windows = []
            price_situation = {'time_pressure': 'low', 'current_opportunities': 0}
        
        # 🎯 STRATEGIC PLANNING
        try:
            now = get_current_ha_time()
            should_update_plan = (
                self._last_plan_update is None or
                (now - self._last_plan_update).total_seconds() > STRATEGIC_PLAN_UPDATE_INTERVAL or
                price_situation.get('time_pressure') in ['high', 'medium']
            )
            
            if should_update_plan:
                _LOGGER.info(f"Strategic Plan: Creating new strategic plan. Last update: {self._last_plan_update}")
                
                currency = self.coordinator.config.get(CONF_CURRENCY, DEFAULT_CURRENCY)
                max_battery_power = self.sensor_helper.get_max_battery_power()
                
                strategic_plan = self.strategic_planner.create_comprehensive_plan(
                    current_state['battery_level'], current_state['battery_capacity'], 
                    max_battery_power, data.get("price_data", {}), 48, currency
                )
                self._last_plan_update = now
                _LOGGER.info(f"🎯 Strategic plan updated: {strategic_plan.scenario} ({len(strategic_plan.operations)} operations)")
            
            strategic_recommendation = self.strategic_planner.get_current_recommendation()
            
            _LOGGER.info(f"🧭 Strategic status: {strategic_recommendation.get('plan_status', 'unknown')}")
            _LOGGER.info(f"🎲 Strategic action: {strategic_recommendation.get('action', 'unknown')} - {strategic_recommendation.get('reason', 'No reason')}")
            
        except Exception as e:
            _LOGGER.warning(f"Strategic planning failed: {e}")
            strategic_recommendation = {
                "action": "hold",
                "reason": "Strategic planning unavailable", 
                "confidence": FALLBACK_CONFIDENCE_LEVEL,
                "plan_status": "error"
            }
        
        return {
            'energy_strategy': energy_strategy,
            'energy_situation': energy_situation,
            'price_windows': price_windows,
            'price_situation': price_situation,
            'strategic_recommendation': strategic_recommendation
        }
    
    def _convert_decision_to_dict(self, decision: DecisionResult) -> Dict[str, Any]:
        """Convert DecisionResult to dictionary format expected by the coordinator."""
        result = {
            "action": decision.action,
            "reason": decision.reason,
            "target_power": decision.target_power,
            "target_battery_level": decision.target_battery_level,
            "profit_forecast": decision.profit_forecast,
            "strategy": decision.strategy,
            "confidence": decision.confidence
        }
        
        if decision.opportunity:
            result["opportunity"] = decision.opportunity
        if decision.plan_status:
            result["plan_status"] = decision.plan_status
        if decision.completion_time:
            result["completion_time"] = decision.completion_time
            
        return result

    def _is_current_time_window(self, time_string: str, tolerance_minutes: int = TIME_WINDOW_TOLERANCE_MINUTES) -> bool:
        try:
            # Use already imported functions
            
            # Parse window time to HA timezone
            window_time = parse_datetime(time_string)
            if not window_time:
                return False
                
            # Get current time in HA timezone
            ha_tz = get_ha_timezone()
            current_time = datetime.now(ha_tz)
            
            time_diff = abs((window_time - current_time).total_seconds() / 60)
            return time_diff <= tolerance_minutes
            
        except Exception:
            return False

    def _get_battery_specs(self, config: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, float]:
        # Get coordinator data for static config parameters  
        coordinator_config = self.sensor_helper.coordinator.data.get('config', {})
        coordinator_options = self.sensor_helper.coordinator.data.get('options', {})
        # Note: config and options parameters kept for API compatibility but using coordinator data
        
        return {
            'capacity': self.sensor_helper.get_battery_capacity(),  # Get current capacity from coordinator via sensor_helper
            'cost': coordinator_options.get('battery_cost', coordinator_config.get('battery_cost', DEFAULT_BATTERY_COST)),
            'cycles': coordinator_options.get('battery_cycles', coordinator_config.get('battery_cycles', DEFAULT_BATTERY_CYCLES)),
            'degradation_factor': coordinator_options.get('degradation_factor', coordinator_config.get('degradation_factor', DEFAULT_DEGRADATION_FACTOR))
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

