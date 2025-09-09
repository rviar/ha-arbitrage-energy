"""
Enhanced ArbitrageOptimizer with ExceptionalPeakDetector integration.
This shows how the peak detection system integrates into the existing architecture.
"""

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
from .peak_detector import ExceptionalPeakDetector
from .peak_decision_handler import PeakAwareDecisionHandler
from .peak_config import PeakConfigManager
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

class EnhancedArbitrageOptimizer:
    """ArbitrageOptimizer with integrated ExceptionalPeakDetector (5-layer architecture)."""
    
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.sensor_helper = SensorDataHelper(coordinator.hass, coordinator.entry.entry_id, coordinator)
        
        # Existing 4-layer components
        self.energy_predictor = EnergyBalancePredictor(self.sensor_helper)
        self.time_analyzer = TimeWindowAnalyzer(self.sensor_helper)
        self.strategic_planner = StrategicPlanner(self.sensor_helper, self.energy_predictor, self.time_analyzer)
        self._last_plan_update = None
        
        # NEW: Layer 5 - Peak Detection System
        self.peak_config_manager = PeakConfigManager(coordinator.hass, coordinator.entry.entry_id)
        peak_config = self.peak_config_manager.get_peak_detection_config(
            coordinator.options, coordinator.config
        )
        self.peak_detector = ExceptionalPeakDetector(self.sensor_helper, peak_config)
        
        # Enhanced decision handlers with peak detection as highest priority
        self.decision_handlers = []
        
        # Add PeakAwareDecisionHandler ONLY if peak detection is enabled
        if self.peak_config_manager.is_peak_detection_enabled(coordinator.options, coordinator.config):
            peak_handler = PeakAwareDecisionHandler(
                self.sensor_helper, self.time_analyzer, peak_config
            )
            self.decision_handlers.append(peak_handler)
            _LOGGER.info("🔬 Peak detection enabled - PeakAwareDecisionHandler added to priority chain")
        
        # Existing decision handlers (maintain original priority order)
        self.decision_handlers.extend([
            StrategicDecisionHandler(self.sensor_helper, self.time_analyzer),
            TimeCriticalDecisionHandler(self.sensor_helper, self.time_analyzer),  
            PredictiveDecisionHandler(self.sensor_helper, self.time_analyzer),
            TraditionalArbitrageHandler(self.sensor_helper, self.time_analyzer),
            HoldDecisionHandler(self.sensor_helper, self.time_analyzer)
        ])
        
        _LOGGER.info(f"🏗️ Enhanced optimizer initialized with {len(self.decision_handlers)} decision handlers")

    @safe_execute(default_return={
        "action": "hold",
        "reason": "Calculation error - using safe defaults",
        "target_power": 0,
        "target_battery_level": FALLBACK_BATTERY_LEVEL_PERCENT,
        "profit_forecast": 0,
        "next_opportunity": None,
        "peak_detection_status": "error"
    })
    @log_performance
    async def calculate_optimal_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced decision calculation with peak detection integration."""
        
        # Log current state for debugging
        self.sensor_helper.log_current_state()
        
        current_state = self._analyze_current_state_from_sensors()
        arbitrage_opportunities = self._find_arbitrage_opportunities_from_sensors(data)
        
        # NEW: Add peak detection information to analysis data
        peak_detection_info = self._gather_peak_detection_info(data)
        data["peak_detection_info"] = peak_detection_info
        
        decision = self._make_decision_from_sensors(current_state, arbitrage_opportunities, data)
        
        # Add peak detection status to decision output
        decision["peak_detection_status"] = peak_detection_info.get("status", "unknown")
        if "peak_result" in peak_detection_info and peak_detection_info["peak_result"]:
            peak_result = peak_detection_info["peak_result"]
            decision["peak_type"] = peak_result.peak_type
            decision["peak_confidence"] = peak_result.confidence
            decision["peak_deviation_factor"] = peak_result.deviation_factor
        
        # Enhanced logging with peak detection info
        peak_status = " | Peak: " + peak_detection_info.get("summary", "none") if peak_detection_info.get("peak_result") else ""
        
        _LOGGER.info(
            f"Enhanced decision: {decision['action']} - {decision['reason']}"
            f" (Battery: {current_state['battery_level']:.1f}%, "
            f"Solar: {current_state['pv_power']:.0f}W, "
            f"Load: {current_state['load_power']:.0f}W){peak_status}"
        )
        
        return decision

    def _gather_peak_detection_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Gather peak detection information for decision making."""
        
        peak_info = {
            "enabled": False,
            "status": "disabled",
            "peak_result": None,
            "detector_stats": None,
            "summary": "Peak detection disabled"
        }
        
        # Check if peak detection is enabled
        if not self.peak_config_manager.is_peak_detection_enabled(
            self.coordinator.options, self.coordinator.config
        ):
            return peak_info
        
        peak_info["enabled"] = True
        peak_info["status"] = "active"
        
        try:
            # Run peak detection
            peak_result = self.peak_detector.detect_exceptional_peaks(data.get("price_data", {}))
            
            # Get detector statistics
            detector_stats = self.peak_detector.get_detection_statistics()
            
            peak_info.update({
                "peak_result": peak_result,
                "detector_stats": detector_stats,
                "status": "completed"
            })
            
            if peak_result:
                peak_info["summary"] = (f"{peak_result.peak_type} "
                                      f"({peak_result.deviation_factor:.2f}x, "
                                      f"{peak_result.time_urgency} urgency)")
                
                _LOGGER.info(f"🔬 Peak detected: {peak_info['summary']}")
            else:
                peak_info["summary"] = "No peaks detected"
                _LOGGER.debug("🔬 Peak detection: No exceptional peaks found")
                
        except Exception as e:
            _LOGGER.error(f"Peak detection failed: {e}")
            peak_info.update({
                "status": "error", 
                "summary": f"Detection error: {str(e)[:50]}"
            })
        
        return peak_info

    # The rest of the methods remain the same as the original optimizer
    # This demonstrates integration without breaking existing functionality
    
    def _analyze_current_state_from_sensors(self) -> Dict[str, Any]:
        """Analyze current state using only sensor data (unchanged from original)."""
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

    def _find_arbitrage_opportunities_from_sensors(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find arbitrage opportunities using sensor data (unchanged from original)."""
        # Get current prices from sensors
        current_buy_price = self.sensor_helper.get_current_buy_price()
        current_sell_price = self.sensor_helper.get_current_sell_price()
        # Get price extremes from MQTT data (will be replaced by price_windows analysis)
        price_data = data.get("price_data", {})
        buy_prices = price_data.get("buy_prices", [])
        sell_prices = price_data.get("sell_prices", [])
        
        # Find current extremes (fallback for traditional arbitrage)
        min_buy_price_24h = min([p.get('value', float('inf')) for p in buy_prices[:PRICE_ANALYSIS_24H_WINDOW]], default=0.0)
        max_sell_price_24h = max([p.get('value', 0) for p in sell_prices[:PRICE_ANALYSIS_24H_WINDOW]], default=0.0)
        
        # Get configuration from sensors
        min_margin = self.sensor_helper.get_min_arbitrage_margin()
        battery_efficiency = self.sensor_helper.get_battery_efficiency()
        
        opportunities = []
        
        # Check immediate arbitrage opportunity
        if current_sell_price > current_buy_price:
            roi = self.sensor_helper.get_arbitrage_roi(current_buy_price, current_sell_price)
            
            if roi >= min_margin:
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
        
        # Sort by ROI
        opportunities.sort(key=lambda x: x['roi_percent'], reverse=True)
        return opportunities

    def _make_decision_from_sensors(
        self, 
        current_state: Dict[str, Any], 
        opportunities: List[Dict[str, Any]], 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhanced decision making with peak detection integration."""
        
        # Check daily cycle limits first (unchanged)
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
        
        # Gather analysis data (includes peak detection info)
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
        
        # Create decision context with peak detection information
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
        
        # Process through ENHANCED decision handlers in priority order
        # Peak detection handler (if enabled) is now FIRST in the chain
        for handler in self.decision_handlers:
            if handler.can_handle(context):
                handler_name = handler.__class__.__name__
                _LOGGER.debug(f"Using {handler_name} for decision")
                decision = handler.make_decision(context)
                if decision:
                    result = self._convert_decision_to_dict(decision)
                    result["decision_handler"] = handler_name  # Track which handler was used
                    return result
        
        # Fallback - should never reach here due to HoldDecisionHandler
        return {
            "action": "hold",
            "reason": "🔄 FALLBACK: No decision handler available",
            "target_power": 0,
            "target_battery_level": current_state['battery_level'],
            "profit_forecast": 0,
            "strategy": "fallback",
            "decision_handler": "fallback"
        }

    def _gather_analysis_data(self, current_state: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced analysis data gathering with peak detection (extends original method)."""
        
        # Run original analysis components
        analysis_data = {}
        
        # 🧠 PREDICTIVE ANALYSIS (unchanged)
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
        
        # 🕐 TIME WINDOW ANALYSIS (unchanged)
        try:
            price_windows = self.time_analyzer.analyze_price_windows(data.get("price_data", {}), PRICE_ANALYSIS_24H_WINDOW)
            price_situation = self.time_analyzer.get_current_price_situation(price_windows)
            
            _LOGGER.info(f"⏰ Price windows found: {len(price_windows)} opportunities")
            _LOGGER.info(f"⚡ Current situation: {price_situation.get('time_pressure', 'low')} time pressure")
            
        except Exception as e:
            _LOGGER.warning(f"Time window analysis failed: {e}")
            price_windows = []
            price_situation = {'time_pressure': 'low', 'current_opportunities': 0}
        
        # 🎯 STRATEGIC PLANNING (unchanged)
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
        
        analysis_data = {
            'energy_strategy': energy_strategy,
            'energy_situation': energy_situation,
            'price_windows': price_windows,
            'price_situation': price_situation,
            'strategic_recommendation': strategic_recommendation
        }
        
        return analysis_data
    
    def _convert_decision_to_dict(self, decision: DecisionResult) -> Dict[str, Any]:
        """Convert DecisionResult to dictionary format (unchanged from original)."""
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

    def _get_battery_specs(self, config: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, float]:
        """Get battery specifications (unchanged from original)."""
        coordinator_config = self.sensor_helper.coordinator.data.get('config', {})
        coordinator_options = self.sensor_helper.coordinator.data.get('options', {})
        
        return {
            'capacity': self.sensor_helper.get_battery_capacity(),
            'cost': coordinator_options.get('battery_cost', coordinator_config.get('battery_cost', DEFAULT_BATTERY_COST)),
            'cycles': coordinator_options.get('battery_cycles', coordinator_config.get('battery_cycles', DEFAULT_BATTERY_CYCLES)),
            'degradation_factor': coordinator_options.get('degradation_factor', coordinator_config.get('degradation_factor', DEFAULT_DEGRADATION_FACTOR))
        }

    def _check_daily_cycle_limits_from_sensors(self, data: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Check daily cycle limits (unchanged from original)."""
        max_daily_cycles = self.sensor_helper.get_max_daily_cycles()
        battery_level = current_state['battery_level']
        
        today_cycles = data.get('today_battery_cycles', 0.0)
        total_cycles = data.get('total_battery_cycles', 0.0)
        
        if today_cycles >= max_daily_cycles:
            return {
                'blocked': True,
                'reason': f"Daily cycle limit reached: {today_cycles:.2f}/{max_daily_cycles} (from sensor)",
                'daily_cycles': today_cycles,
                'max_cycles': max_daily_cycles,
                'total_cycles': total_cycles
            }
        
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

    # NEW: Peak detection specific methods
    def get_peak_detection_status(self) -> Dict[str, Any]:
        """Get comprehensive peak detection status."""
        if not self.peak_config_manager.is_peak_detection_enabled(
            self.coordinator.options, self.coordinator.config
        ):
            return {"enabled": False, "reason": "Peak detection disabled in configuration"}
        
        try:
            # Get the peak handler from decision handlers
            peak_handler = None
            for handler in self.decision_handlers:
                if isinstance(handler, PeakAwareDecisionHandler):
                    peak_handler = handler
                    break
            
            if peak_handler:
                return {
                    "enabled": True,
                    "status": peak_handler.get_peak_detection_status(),
                    "detector_stats": self.peak_detector.get_detection_statistics()
                }
            else:
                return {"enabled": False, "reason": "Peak handler not found in decision chain"}
                
        except Exception as e:
            return {"enabled": False, "reason": f"Error getting status: {str(e)}"}

    def reconfigure_peak_detection(self):
        """Reconfigure peak detection system with updated settings."""
        if not self.peak_config_manager.is_peak_detection_enabled(
            self.coordinator.options, self.coordinator.config
        ):
            _LOGGER.info("🔬 Peak detection disabled - removing from decision chain")
            # Remove peak handlers from decision chain
            self.decision_handlers = [h for h in self.decision_handlers 
                                    if not isinstance(h, PeakAwareDecisionHandler)]
            return
        
        # Get updated configuration
        new_config = self.peak_config_manager.get_peak_detection_config(
            self.coordinator.options, self.coordinator.config
        )
        
        # Update existing peak detector configuration
        self.peak_detector.configure(new_config)
        
        # Update peak handler configuration
        for handler in self.decision_handlers:
            if isinstance(handler, PeakAwareDecisionHandler):
                handler.configure_peak_detection(new_config)
                break
        else:
            # No peak handler found - add one
            peak_handler = PeakAwareDecisionHandler(
                self.sensor_helper, self.time_analyzer, new_config
            )
            self.decision_handlers.insert(0, peak_handler)
            _LOGGER.info("🔬 Peak detection enabled - added PeakAwareDecisionHandler to decision chain")
        
        _LOGGER.info("🔬 Peak detection system reconfigured")