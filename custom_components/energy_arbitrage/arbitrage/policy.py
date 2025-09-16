"""
Unified policy functions for arbitrage gating and reserves.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from .utils import get_current_ha_time
from .constants import (
    MIN_TRADE_ENERGY_WH, TRADE_COOLDOWN_MINUTES, MIN_SPREAD_PERCENT,
    SURPLUS_POWER_IGNORE_W, PV_SURPLUS_BLOCK_MARGIN_PERCENT
)

_LOGGER = logging.getLogger(__name__)

def is_on_cooldown(last_trade_ts_iso: str, action: str) -> bool:
    """Check if we are within cooldown for a given trade action."""
    if not last_trade_ts_iso:
        return False
    try:
        last_ts = datetime.fromisoformat(last_trade_ts_iso)
    except Exception:
        return False
    now = get_current_ha_time()
    return (now - last_ts) < timedelta(minutes=TRADE_COOLDOWN_MINUTES)


def can_sell_now(context: Dict[str, Any]) -> Dict[str, Any]:
    """Unified sell gating logic; returns dict with allowed flag and reason."""
    analysis = context.get('analysis', {})
    price_situation = analysis.get('price_situation', {})
    near_term = analysis.get('near_term_rebuy', {})
    current_state = context.get('current_state', {})
    opportunities = context.get('opportunities', [])

    available_battery = current_state.get('available_battery_capacity', 0)
    if available_battery < MIN_TRADE_ENERGY_WH:
        return {'allowed': False, 'reason': 'insufficient_energy'}

    immediate = price_situation.get('immediate_action')
    has_immediate_sell = False
    if opportunities and immediate and immediate.get('action') == 'sell':
        has_immediate_sell = any(o.get('is_immediate_sell') for o in opportunities)

    has_near_term = near_term.get('has_opportunity', False)
    if not has_immediate_sell and not has_near_term:
        return {'allowed': False, 'reason': 'no_immediate_or_near_term'}

    return {'allowed': True, 'reason': 'ok'}


def can_buy_now(context: Dict[str, Any]) -> Dict[str, Any]:
    """Unified buy gating logic; returns dict with allowed flag and reason."""
    analysis = context.get('analysis', {})
    price_situation = analysis.get('price_situation', {})
    current_state = context.get('current_state', {})
    energy_strategy = analysis.get('energy_strategy', {})
    opportunities = context.get('opportunities', [])

    # Ensure there is battery headroom
    battery_level = current_state.get('battery_level', 50.0)
    battery_capacity = current_state.get('battery_capacity', 10000)
    min_reserve_percent = current_state.get('min_reserve_percent', 20)
    max_wh = battery_capacity * (1.0 - min_reserve_percent / 100.0)
    current_wh = battery_capacity * battery_level / 100.0
    if max_wh - current_wh < MIN_TRADE_ENERGY_WH:
        return {'allowed': False, 'reason': 'insufficient_headroom'}

    # PV surplus guard: do not buy if PV already covers (or almost covers) the load
    pv_power = current_state.get('pv_power', 0)
    load_power = current_state.get('load_power', 0)
    net_surplus = max(0, pv_power - load_power)
    immediate = price_situation.get('immediate_action') or {}
    time_remaining_h = immediate.get('time_remaining', 1.0)
    required_wh_to_target = analysis.get('required_wh_to_target', 0.0)
    potential_surplus_wh = net_surplus * time_remaining_h
    # If current PV surplus over the duration of the buy window can meaningfully charge toward the target, block buying now
    if net_surplus > SURPLUS_POWER_IGNORE_W and potential_surplus_wh >= min(MIN_TRADE_ENERGY_WH, max(0.0, required_wh_to_target)):
        return {'allowed': False, 'reason': 'pv_surplus_now'}

    # Forecast guard: if PV surplus (storeable) can cover required energy to reach target, don't buy
    if analysis.get('pv_can_reach_target') is True:
        return {'allowed': False, 'reason': 'pv_forecast_will_charge'}

    immediate = price_situation.get('immediate_action')
    if not immediate or immediate.get('action') != 'buy':
        return {'allowed': False, 'reason': 'no_immediate_buy'}

    # ROI gating: require an ROI-qualified immediate buy opportunity
    has_immediate_buy = False
    if opportunities:
        has_immediate_buy = any(o.get('is_immediate_buy') for o in opportunities)
    if not has_immediate_buy:
        return {'allowed': False, 'reason': 'no_immediate_roi_buy'}

    return {'allowed': True, 'reason': 'ok'}


