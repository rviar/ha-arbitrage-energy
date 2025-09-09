"""
Peak Override Decision Handler for Exceptional Price Opportunities
Handles immediate action decisions when exceptional peaks are detected.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from .decision_handlers import DecisionHandler, DecisionContext
from .peak_detector import ExceptionalPeakDetector, PeakType
from .constants import (
    DECISION_PRIORITY_EXCEPTIONAL_PEAK, CONFIDENCE_HIGH, MAX_BATTERY_LEVEL,
    PEAK_DETECTION_MAX_POWER_PERCENTAGE, MIN_ENERGY_FOR_SELL
)
from .utils import get_current_ha_time
from .exceptions import safe_execute

_LOGGER = logging.getLogger(__name__)

class PeakOverrideDecisionHandler(DecisionHandler):
    """
    Decision handler for exceptional peak override scenarios.
    
    This handler has the highest priority (0) and can override strategic plans
    when exceptional market opportunities are detected.
    """
    
    priority = DECISION_PRIORITY_EXCEPTIONAL_PEAK
    handler_name = "exceptional_peak_override"
    
    def __init__(self, peak_detector: ExceptionalPeakDetector):
        super().__init__()
        self.peak_detector = peak_detector
        self._last_action_time: Optional[datetime] = None
        
    @safe_execute(default_return=False)
    def can_handle(self, context: DecisionContext) -> bool:
        """
        Check if this handler can process the current context.
        
        Only handles situations when:
        1. Peak detection is enabled
        2. Current prices indicate exceptional opportunity
        3. Battery has sufficient capacity for action
        """
        if not self.peak_detector.is_enabled():
            return False
        
        # Must have current price data
        if not context.current_state or 'current_sell_price' not in context.current_state:
            return False
        
        current_sell_price = context.current_state.get('current_sell_price', 0.0)
        if current_sell_price <= 0:
            return False
        
        # Check if we have a strategic plan to potentially override
        strategic_plan = getattr(context, 'strategic_plan', None)
        strategic_price = None
        if strategic_plan and hasattr(strategic_plan, 'next_operation') and strategic_plan.next_operation:
            strategic_price = strategic_plan.next_operation.expected_price
        
        # Analyze current price for exceptional conditions
        analysis = self.peak_detector.analyze_current_price(current_sell_price, strategic_price)
        
        # Can handle if this is an exceptional peak requiring override
        can_handle = analysis.is_exceptional and analysis.should_override
        
        if can_handle:
            _LOGGER.info(f"🚨 Peak override handler activated: {analysis.peak_type.value} - urgency {analysis.urgency}")
        
        return can_handle
    
    @safe_execute(default_return={
        "action": "hold",
        "reason": "Peak detection failed - safe mode",
        "confidence": 0.0,
        "target_battery_level": None,
        "target_power_w": 0,
        "urgency": "low",
        "override_strategic": False
    })
    def handle(self, context: DecisionContext) -> Dict[str, Any]:
        """
        Handle exceptional peak opportunity with immediate action.
        
        Returns decision to immediately sell energy at peak prices,
        potentially overriding strategic plans.
        """
        current_state = context.current_state
        battery_level = current_state.get('battery_level', 0.0)
        current_sell_price = current_state.get('current_sell_price', 0.0)
        available_battery_wh = current_state.get('available_battery_wh', 0.0)
        max_battery_power = context.system_constraints.get('max_battery_power', 5000.0)
        min_reserve = context.system_constraints.get('min_reserve_percent', 20.0)
        
        # Get strategic plan details
        strategic_plan = getattr(context, 'strategic_plan', None)
        strategic_price = None
        if strategic_plan and hasattr(strategic_plan, 'next_operation') and strategic_plan.next_operation:
            strategic_price = strategic_plan.next_operation.expected_price
        
        # Analyze peak characteristics
        analysis = self.peak_detector.analyze_current_price(current_sell_price, strategic_price)
        
        # Determine action based on peak type and urgency
        action_decision = self._determine_peak_action(analysis, current_state, context)
        
        # Log the override decision
        self._log_override_decision(analysis, action_decision, strategic_plan)
        
        # Record action time for cooldown tracking
        self._last_action_time = get_current_ha_time()
        
        return action_decision
    
    def _determine_peak_action(self, analysis, current_state: Dict[str, Any], context: DecisionContext) -> Dict[str, Any]:
        """Determine specific action based on peak analysis."""
        battery_level = current_state.get('battery_level', 0.0)
        available_battery_wh = current_state.get('available_battery_wh', 0.0)
        max_battery_power = context.system_constraints.get('max_battery_power', 5000.0)
        min_reserve = context.system_constraints.get('min_reserve_percent', 20.0)
        
        # Base decision structure
        decision = {
            "action": "sell",
            "reason": f"🚨 PEAK OVERRIDE: {analysis.peak_type.value.replace('_', ' ').title()}",
            "confidence": analysis.confidence,
            "urgency": analysis.urgency,
            "override_strategic": True,
            "peak_analysis": {
                "peak_type": analysis.peak_type.value,
                "current_price": analysis.current_price,
                "z_score": analysis.z_score,
                "deviation_ratio": analysis.deviation_ratio,
                "profit_multiplier": analysis.profit_multiplier
            }
        }
        
        # Check if battery has sufficient energy to sell
        if battery_level <= min_reserve + 10:  # 10% buffer above reserve
            decision.update({
                "action": "hold",
                "reason": f"🚨 PEAK DETECTED but battery too low: {battery_level:.1f}% < {min_reserve + 10:.1f}%",
                "confidence": 0.1,
                "target_battery_level": battery_level,
                "target_power_w": 0
            })
            return decision
        
        if available_battery_wh < MIN_ENERGY_FOR_SELL:
            decision.update({
                "action": "hold", 
                "reason": f"🚨 PEAK DETECTED but insufficient energy: {available_battery_wh:.0f}Wh < {MIN_ENERGY_FOR_SELL}Wh",
                "confidence": 0.1,
                "target_battery_level": battery_level,
                "target_power_w": 0
            })
            return decision
        
        # Determine power and target based on peak characteristics
        if analysis.peak_type == PeakType.EXTREME_PEAK or analysis.urgency == "critical":
            # Maximum power discharge for extreme peaks
            power_multiplier = PEAK_DETECTION_MAX_POWER_PERCENTAGE / 100.0
            target_battery_level = max(min_reserve, min_reserve + 5)  # Discharge to near reserve
            
            decision.update({
                "reason": f"🚨 EXTREME PEAK: {analysis.current_price:.4f} PLN/kWh (z={analysis.z_score:.2f})",
                "target_battery_level": target_battery_level,
                "target_power_w": int(max_battery_power * power_multiplier),
                "urgency": "critical"
            })
            
        elif analysis.peak_type == PeakType.STRATEGIC_OVERRIDE:
            # Moderate power for strategic overrides
            power_multiplier = 0.75  # 75% power
            target_battery_level = max(min_reserve, battery_level - 20)  # Discharge 20% of battery
            
            decision.update({
                "reason": f"⚡ STRATEGIC OVERRIDE: {analysis.current_price:.4f} vs planned {analysis.baseline_mean:.4f} PLN/kWh",
                "target_battery_level": target_battery_level,
                "target_power_w": int(max_battery_power * power_multiplier),
                "urgency": "high"
            })
            
        else:  # Statistical outlier
            # Conservative power for statistical outliers
            power_multiplier = 0.60  # 60% power
            target_battery_level = max(min_reserve, battery_level - 15)  # Discharge 15% of battery
            
            decision.update({
                "reason": f"📊 STATISTICAL PEAK: {analysis.current_price:.4f} PLN/kWh (z={analysis.z_score:.2f})",
                "target_battery_level": target_battery_level, 
                "target_power_w": int(max_battery_power * power_multiplier),
                "urgency": "high"
            })
        
        # Ensure target doesn't exceed available capacity
        max_discharge = min(available_battery_wh / 1000, max_battery_power / 1000)  # kW
        decision["target_power_w"] = min(decision["target_power_w"], int(max_discharge * 1000))
        
        return decision
    
    def _log_override_decision(self, analysis, decision: Dict[str, Any], strategic_plan):
        """Log detailed information about override decision."""
        _LOGGER.warning(
            f"🚨 PEAK OVERRIDE ACTIVATED:\n"
            f"   Peak Type: {analysis.peak_type.value}\n" 
            f"   Price: {analysis.current_price:.4f} PLN/kWh\n"
            f"   Z-Score: {analysis.z_score:.2f}\n"
            f"   Deviation: {analysis.deviation_ratio:.2f}x baseline\n"
            f"   Confidence: {analysis.confidence:.2f}\n"
            f"   Action: {decision['action']} at {decision.get('target_power_w', 0)}W\n"
            f"   Target Level: {decision.get('target_battery_level', 'N/A')}%\n"
            f"   Urgency: {decision['urgency']}"
        )
        
        if strategic_plan and hasattr(strategic_plan, 'next_operation') and strategic_plan.next_operation:
            next_op = strategic_plan.next_operation
            _LOGGER.warning(
                f"   Strategic Plan Override:\n"
                f"     Planned Price: {next_op.expected_price:.4f} PLN/kWh\n"
                f"     Planned Time: {next_op.start_time}\n"
                f"     Profit Enhancement: {analysis.profit_multiplier:.1f}x"
            )
    
    def get_handler_status(self) -> Dict[str, Any]:
        """Get status information for monitoring."""
        return {
            "handler_name": self.handler_name,
            "priority": self.priority,
            "peak_detection_enabled": self.peak_detector.is_enabled(),
            "last_action_time": self._last_action_time.isoformat() if self._last_action_time else None,
            "peak_statistics": self.peak_detector.get_peak_statistics()
        }