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
    STRATEGIC_CHARGE_LEVEL_ADJUSTMENT,
    STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT, MIN_ENERGY_FOR_SELL,
    PRICE_COMPARISON_TOLERANCE
)
from .policy import can_sell_now, can_buy_now
from .utils import get_current_ha_time
 

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
        # Simplified: act whenever there is an immediate action window, no urgency dependency
        return context.price_situation.get('immediate_action') is not None
    
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
            # Enforce strict top-1 (lowest) among future buy windows
            try:
                analysis = context.data.get('analysis', {}) or {}
                windows = analysis.get('price_windows', []) or []
                # Find current buy window
                current_buy_win = next((w for w in windows if getattr(w, 'action', None) == 'buy' and w.is_current), None)
                # Find best (lowest price) buy window for TODAY first; fallback to horizon if none
                now_date = get_current_ha_time().date()
                todays = [w for w in windows if getattr(w, 'action', None) == 'buy' and (w.is_current or w.is_upcoming) and w.start_time.date() == now_date]
                future_buy_windows = todays or [w for w in windows if getattr(w, 'action', None) == 'buy' and (w.is_current or w.is_upcoming)]
                future_buy_windows.sort(key=lambda w: (w.price, w.start_time))
                best_future_buy = future_buy_windows[0] if future_buy_windows else None
                # Compute headroom and apply reserve-for-top1 logic
                battery_capacity = context.current_state.get('battery_capacity', 0.0)
                current_wh = (battery_level / 100.0) * battery_capacity
                headroom_wh = max(0.0, battery_capacity - current_wh)

                # Determine if current is effectively top-1 (within tolerance)
                if current_buy_win and best_future_buy and (best_future_buy.price <= current_buy_win.price + PRICE_COMPARISON_TOLERANCE):
                    # Current is top-1 → use full 1h capacity
                    charge_power = min(context.max_battery_power, headroom_wh)
                    if charge_power >= 100:
                        return DecisionResult(
                            action="charge_arbitrage",
                            reason=f"{urgency_prefix}: BUY now (top-1 hour)",
                            target_power=charge_power,
                            target_battery_level=min(MAX_BATTERY_LEVEL, battery_level + STRATEGIC_CHARGE_LEVEL_ADJUSTMENT),
                            profit_forecast=(best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (charge_power / 1000),
                            opportunity=best_opportunity,
                            strategy="time_critical_top3",
                            plan_status="immediate"
                        )
                else:
                    # Current is not top-1 → reserve 1h for top-1, use only excess now
                    reserve_wh = min(context.max_battery_power, headroom_wh)
                    allowed_now_wh = max(0.0, headroom_wh - reserve_wh)
                    charge_power = min(context.max_battery_power, allowed_now_wh)
                    if charge_power >= 100:
                        return DecisionResult(
                            action="charge_arbitrage",
                            reason=f"{urgency_prefix}: BUY now (reserving top-1)",
                            target_power=charge_power,
                            target_battery_level=min(MAX_BATTERY_LEVEL, battery_level + STRATEGIC_CHARGE_LEVEL_ADJUSTMENT),
                            profit_forecast=(best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (charge_power / 1000),
                            opportunity=best_opportunity,
                            strategy="time_critical_top3",
                            plan_status="immediate"
                        )
                    # Not enough excess → wait for top-1
                    analysis['last_policy_reason'] = 'waiting_top1_buy'
                    return None
            except Exception:
                pass
            return None
            
        elif (immediate['action'] == 'sell' and 
              available_battery > MIN_ENERGY_FOR_SELL and
              sell_policy.get('allowed')):
            # Enforce strict top-1 (highest) among future sell windows
            try:
                analysis = context.data.get('analysis', {}) or {}
                windows = analysis.get('price_windows', []) or []
                # Find current sell window
                current_sell_win = next((w for w in windows if getattr(w, 'action', None) == 'sell' and w.is_current), None)
                # Find best (highest price) sell window for TODAY first; fallback to horizon if none
                now_date = get_current_ha_time().date()
                todays = [w for w in windows if getattr(w, 'action', None) == 'sell' and (w.is_current or w.is_upcoming) and w.start_time.date() == now_date]
                future_sell_windows = todays or [w for w in windows if getattr(w, 'action', None) == 'sell' and (w.is_current or w.is_upcoming)]
                future_sell_windows.sort(key=lambda w: (-w.price, w.start_time))
                best_future_sell = future_sell_windows[0] if future_sell_windows else None
                # Determine if current is effectively top-1 (within tolerance)
                if current_sell_win and best_future_sell and (best_future_sell.price <= current_sell_win.price + PRICE_COMPARISON_TOLERANCE):
                    # Current is top-1 → use full 1h capacity
                    discharge_power = min(context.max_battery_power, available_battery)
                    if discharge_power >= 100:
                        return DecisionResult(
                            action="sell_arbitrage",
                            reason=f"{urgency_prefix}: SELL now (top-1 hour)",
                            target_power=-discharge_power,
                            target_battery_level=max(min_reserve, battery_level - STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT),
                            profit_forecast=((best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (discharge_power / 1000)),
                            opportunity=best_opportunity,
                            strategy="time_critical_top3",
                            plan_status="immediate"
                        )
                else:
                    # Current is not top-1 → reserve 1h for top-1, use only excess now
                    reserve_wh = min(context.max_battery_power, available_battery)
                    allowed_now_wh = max(0.0, available_battery - reserve_wh)
                    discharge_power = min(context.max_battery_power, allowed_now_wh)
                    if discharge_power >= 100:
                        return DecisionResult(
                            action="sell_arbitrage",
                            reason=f"{urgency_prefix}: SELL now (reserving top-1)",
                            target_power=-discharge_power,
                            target_battery_level=max(min_reserve, battery_level - STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT),
                            profit_forecast=((best_opportunity.get('net_profit_per_kwh', 0) if best_opportunity else 0) * (discharge_power / 1000)),
                            opportunity=best_opportunity,
                            strategy="time_critical_top3",
                            plan_status="immediate"
                        )
                    # Not enough excess → wait for top-1
                    analysis['last_policy_reason'] = 'waiting_top1_sell'
                    return None
            except Exception:
                pass
            return None

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

# PredictiveDecisionHandler removed per top-3 simplification

class HoldDecisionHandler(DecisionHandler):
    """Handles hold/wait decisions when no profitable opportunities exist."""
    
    def can_handle(self, context: DecisionContext) -> bool:
        return True  # Always can handle (fallback)
    
    def make_decision(self, context: DecisionContext) -> Optional[DecisionResult]:
        battery_level = context.current_state['battery_level']
        
        # Prefer detailed policy reason if available; otherwise use price-situation context, then strategy
        analysis = context.data.get('analysis', {})
        policy_reason = analysis.get('last_policy_reason')
        price_situation = analysis.get('price_situation', {})
        next_opp = price_situation.get('next_opportunity')

        if policy_reason:
            reason = f"🔄 HOLD: {policy_reason}"
        elif not price_situation.get('immediate_action') and next_opp:
            reason = (
                f"🔄 HOLD: waiting_next_window {next_opp.get('action')} in "
                f"{next_opp.get('time_until_start', 0):.1f}h"
            )
        elif context.energy_strategy.get('recommendation') == 'hold':
            hold_reason = context.energy_strategy.get('reason') or 'Waiting for better conditions'
            reason = f"🔄 HOLD: {hold_reason}"
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