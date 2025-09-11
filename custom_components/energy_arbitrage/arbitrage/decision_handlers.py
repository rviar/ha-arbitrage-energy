"""
Decision handlers for energy arbitrage optimization.
Breaks down complex decision logic into focused, testable components.
"""

import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass
from .constants import (
    MAX_BATTERY_LEVEL,
    BATTERY_POWER_CONSERVATIVE_MULTIPLIER, STRATEGIC_CHARGE_LEVEL_ADJUSTMENT,
    STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT, MIN_ENERGY_FOR_SELL,
    BATTERY_CHARGE_AGGRESSIVE_MARGIN
)
from .policy import can_sell_now, can_buy_now

_LOGGER = logging.getLogger(__name__)

@dataclass
class DecisionContext:
    """Context data for making arbitrage decisions."""
    current_state: Dict[str, Any]
    opportunities: List[Dict[str, Any]]
    data: Dict[str, Any]
    max_battery_power: float
    min_arbitrage_margin: float
    energy_strategy: Dict[str, Any]
    price_situation: Dict[str, Any]

@dataclass 
class DecisionResult:
    """Result of an arbitrage decision."""
    action: str
    reason: str
    target_power: float
    target_battery_level: float
    profit_forecast: float
    opportunity: Optional[Dict[str, Any]] = None
    strategy: str = "unknown"
    confidence: float = 0.5
    plan_status: Optional[str] = None
    completion_time: Optional[str] = None

class DecisionHandler(ABC):
    """Base class for decision handlers."""
    
    def __init__(self, sensor_helper, time_analyzer):
        self.sensor_helper = sensor_helper
        self.time_analyzer = time_analyzer
    
    @abstractmethod
    def can_handle(self, context: DecisionContext) -> bool:
        """Check if this handler can process the given context."""
        pass
    
    @abstractmethod 
    def make_decision(self, context: DecisionContext) -> Optional[DecisionResult]:
        """Make a decision based on the context."""
        pass

# StrategicDecisionHandler removed (planner deprecated)

class TimeCriticalDecisionHandler(DecisionHandler):
    """Handles time-sensitive arbitrage opportunities."""
    
    def can_handle(self, context: DecisionContext) -> bool:
        return (
            context.price_situation.get('time_pressure') in ['high', 'medium'] and
            context.price_situation.get('immediate_action') is not None
        )
    
    def make_decision(self, context: DecisionContext) -> Optional[DecisionResult]:
        immediate = context.price_situation['immediate_action']
        battery_level = context.current_state['battery_level']
        min_reserve = context.current_state['min_reserve_percent']
        surplus_power = max(0, context.current_state['pv_power'] - context.current_state['load_power'])
        available_battery = context.current_state.get('available_battery_capacity', 0)
        # Prefer opportunity matching the immediate action to avoid future ROI mismatch
        if context.opportunities:
            if immediate['action'] == 'sell':
                best_opportunity = next((o for o in context.opportunities if o.get('is_immediate_sell')), context.opportunities[0])
            else:
                best_opportunity = next((o for o in context.opportunities if o.get('is_immediate_buy')), context.opportunities[0])
        else:
            best_opportunity = None
        
        urgency_prefix = "⚡ CRITICAL" if context.price_situation.get('time_pressure') == 'high' else "🚨 URGENT"
        
        buy_policy = can_buy_now({'analysis': context.data.get('analysis', {}), 'current_state': context.current_state})
        sell_policy = can_sell_now({
            'analysis': context.data.get('analysis', {}),
            'current_state': context.current_state,
            'opportunities': context.opportunities
        })
        if (immediate['action'] == 'buy' and 
            self.sensor_helper.is_battery_charging_viable() and 
            buy_policy.get('allowed')):
            
            charge_power = min(context.max_battery_power, 
                             surplus_power if surplus_power > 0 else context.max_battery_power)
            
            decision = DecisionResult(
                action="charge_arbitrage",
                reason=f"{urgency_prefix}: Buy window ending in {immediate['time_remaining']:.1f}h (Price: {immediate['price']:.3f})",
                target_power=charge_power,
                target_battery_level=min(MAX_BATTERY_LEVEL, battery_level + STRATEGIC_CHARGE_LEVEL_ADJUSTMENT),
                profit_forecast=best_opportunity.get('net_profit_per_kwh', 0) * (charge_power / 1000),
                opportunity=best_opportunity,
                strategy="time_critical"
            )
            _LOGGER.debug(f"TimeCritical BUY approved: reason={buy_policy.get('reason')}")
            return decision
            
        elif (immediate['action'] == 'sell' and 
              available_battery > MIN_ENERGY_FOR_SELL and
              sell_policy.get('allowed')):
            
            discharge_power = min(context.max_battery_power, 
                                available_battery / immediate['time_remaining'])
            
            decision = DecisionResult(
                action="sell_arbitrage",
                reason=f"{urgency_prefix}: Sell window ending in {immediate['time_remaining']:.1f}h (Price: {immediate['price']:.3f})",
                target_power=-discharge_power,
                target_battery_level=max(min_reserve, battery_level - STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT),
                profit_forecast=((best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (discharge_power / 1000)),
                opportunity=best_opportunity,
                strategy="time_critical"
            )
            _LOGGER.debug(f"TimeCritical SELL approved: reason={sell_policy.get('reason')}")
            return decision

        # If we get here, store policy reason for HOLD to explain why action was skipped
        try:
            analysis = context.data.get('analysis', {})
            if immediate['action'] == 'buy' and not buy_policy.get('allowed'):
                analysis['last_policy_reason'] = buy_policy.get('reason', 'policy_blocked')
            elif immediate['action'] == 'sell' and not sell_policy.get('allowed'):
                analysis['last_policy_reason'] = sell_policy.get('reason', 'policy_blocked')
        except Exception:
            pass
        
        return None

class PredictiveDecisionHandler(DecisionHandler):
    """Handles energy forecast-based predictive decisions."""
    
    def can_handle(self, context: DecisionContext) -> bool:
        return (
            context.energy_strategy['recommendation'] in ['charge_aggressive', 'charge_moderate', 'sell_aggressive', 'sell_partial'] and
            context.opportunities
        )
    
    def make_decision(self, context: DecisionContext) -> Optional[DecisionResult]:
        strategy = context.energy_strategy
        battery_level = context.current_state['battery_level']
        battery_capacity = context.current_state['battery_capacity']
        min_reserve = context.current_state['min_reserve_percent']
        surplus_power = max(0, context.current_state['pv_power'] - context.current_state['load_power'])
        available_battery = context.current_state.get('available_battery_capacity', 0)
        best_opportunity = context.opportunities[0] if context.opportunities else None
        
        if strategy['recommendation'] in ['charge_aggressive', 'charge_moderate']:
            return self._handle_charge_strategy(context, strategy, battery_level, battery_capacity, 
                                              surplus_power, best_opportunity)
        
        elif strategy['recommendation'] in ['sell_aggressive', 'sell_partial']:
            return self._handle_sell_strategy(context, strategy, battery_level, min_reserve, 
                                            available_battery, best_opportunity)
        
        return None
    
    def _handle_charge_strategy(self, context, strategy, battery_level, battery_capacity, surplus_power, best_opportunity):
        if not (best_opportunity and best_opportunity.get('is_immediate_buy')):
            return None
            
        # For aggressive charging, use lower margin threshold
        margin_multiplier = BATTERY_CHARGE_AGGRESSIVE_MARGIN if strategy['recommendation'] == 'charge_aggressive' else 1.0
        if best_opportunity['roi_percent'] < context.min_arbitrage_margin * margin_multiplier:
            return None
        
        target_energy = (strategy['target_battery_level'] - battery_level) / 100 * battery_capacity
        
        # Try to plan the operation  
        try:
            # Get price windows from the analysis data that was passed through context
            # We need to access it through the data since it's computed in gather_analysis_data
            price_windows = context.data.get('analysis', {}).get('price_windows', [])
            planned_operation = self.time_analyzer.plan_battery_operation(
                target_energy, 'charge', price_windows, context.max_battery_power,
                context.data.get("price_data", {}).get("buy_prices", [])
            )
            
            if planned_operation and planned_operation.feasible:
                priority_label = "⚡ PLANNED" if strategy['recommendation'] == 'charge_aggressive' else "📊 PLANNED"
                return DecisionResult(
                    action="charge_arbitrage",
                    reason=f"{priority_label}: {strategy['reason']} (Time: {planned_operation.duration_hours:.1f}h, ROI: {best_opportunity['roi_percent']:.1f}%)",
                    target_power=planned_operation.target_power_w,
                    target_battery_level=strategy['target_battery_level'],
                    profit_forecast=best_opportunity['net_profit_per_kwh'] * (planned_operation.target_power_w / 1000),
                    opportunity=best_opportunity,
                    strategy=f"{strategy['recommendation']}_planned",
                    completion_time=planned_operation.completion_time.isoformat()
                )
        except Exception as e:
            _LOGGER.warning(f"Failed to plan battery operation: {e}")
        
        # Fallback to immediate charging
        charge_power = min(context.max_battery_power, surplus_power if surplus_power > 0 else context.max_battery_power)
        priority_label = "⚡ IMMEDIATE" if strategy['recommendation'] == 'charge_aggressive' else "📊 STANDARD"
        target_adjustment = 15 if strategy['recommendation'] == 'charge_aggressive' else 10
        
        return DecisionResult(
            action="charge_arbitrage", 
            reason=f"{priority_label}: {strategy['reason']} (ROI: {best_opportunity['roi_percent']:.1f}%)",
            target_power=charge_power,
            target_battery_level=min(95, battery_level + target_adjustment),
            profit_forecast=best_opportunity['net_profit_per_kwh'] * (charge_power / 1000),
            opportunity=best_opportunity,
            strategy=strategy['recommendation']
        )
    
    def _handle_sell_strategy(self, context, strategy, battery_level, min_reserve, available_battery, best_opportunity):
        sell_policy = can_sell_now({
            'analysis': context.data.get('analysis', {}),
            'current_state': context.current_state,
            'opportunities': context.opportunities
        })
        if not (available_battery > MIN_ENERGY_FOR_SELL and sell_policy.get('allowed')):
            _LOGGER.debug(f"Predictive sell skipped: reason={sell_policy.get('reason', 'unknown')}")
            # Store policy reason for HOLD context
            try:
                context.data.get('analysis', {})['last_policy_reason'] = sell_policy.get('reason', 'policy_blocked')
            except Exception:
                pass
            return None
        
        # Calculate discharge parameters based on strategy
        if strategy['recommendation'] == 'sell_aggressive':
            discharge_power = min(context.max_battery_power, available_battery / 2)  # Aggressive discharge
            target_adjustment = 20
        else:  # sell_partial
            discharge_power = min(context.max_battery_power * 0.6, available_battery / 3)  # Conservative discharge
            target_adjustment = 10
        
        priority_label = "🔥 AGGRESSIVE" if strategy['recommendation'] == 'sell_aggressive' else "📈 SELECTIVE"
        
        return DecisionResult(
            action="sell_arbitrage",
            reason=f"{priority_label}: {strategy['reason']} (ROI: {(best_opportunity['roi_percent'] if best_opportunity else context.data.get('analysis', {}).get('near_term_rebuy', {}).get('roi_percent', 0)):.1f}%)",
            target_power=-discharge_power,
            target_battery_level=max(min_reserve, battery_level - target_adjustment),
            profit_forecast=((best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (discharge_power / 1000)),
            opportunity=best_opportunity,
            strategy=strategy['recommendation']
        )

class HoldDecisionHandler(DecisionHandler):
    """Handles hold/wait decisions when no profitable opportunities exist."""
    
    def can_handle(self, context: DecisionContext) -> bool:
        return True  # Always can handle (fallback)
    
    def make_decision(self, context: DecisionContext) -> Optional[DecisionResult]:
        battery_level = context.current_state['battery_level']
        
        # Prefer detailed policy reason if available
        policy_reason = context.data.get('analysis', {}).get('last_policy_reason')
        if policy_reason:
            reason = f"🔄 HOLD: {policy_reason}"
        elif context.energy_strategy.get('recommendation') == 'hold':
            reason = f"🔄 STRATEGIC HOLD: {context.energy_strategy.get('reason', 'Waiting for better conditions')}"
        else:
            reason = "🔄 HOLD: No profitable opportunities available"
        
        return DecisionResult(
            action="hold",
            reason=reason,
            target_power=0,
            target_battery_level=battery_level,
            profit_forecast=0,
            strategy="hold"
        )