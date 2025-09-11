"""
Unified policy functions for arbitrage gating and reserves.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from .utils import get_current_ha_time
from .constants import (
    MIN_TRADE_ENERGY_WH, TRADE_COOLDOWN_MINUTES, MIN_SPREAD_PERCENT
)

_LOGGER = logging.getLogger(__name__)


def compute_min_reserve_percent(energy_situation: str, user_min_reserve_percent: float) -> float:
    """Derive dynamic minimum reserve percent based on energy situation."""
    # If abundant energy (both days surplus), allow lower reserve; else keep user minimum
    if energy_situation == 'abundant_energy':
        return max(40.0, user_min_reserve_percent)
    return user_min_reserve_percent


def meets_min_spread_percent(buy_price: float, sell_price: float) -> bool:
    """Ensure minimum spread between sell and buy to justify a trade."""
    if buy_price <= 0 or sell_price <= 0:
        return False
    spread = (sell_price - buy_price) / buy_price * 100.0
    return spread >= MIN_SPREAD_PERCENT


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

    # Ensure there is battery headroom
    battery_level = current_state.get('battery_level', 50.0)
    battery_capacity = current_state.get('battery_capacity', 10000)
    min_reserve_percent = current_state.get('min_reserve_percent', 20)
    max_wh = battery_capacity * (1.0 - min_reserve_percent / 100.0)
    current_wh = battery_capacity * battery_level / 100.0
    if max_wh - current_wh < MIN_TRADE_ENERGY_WH:
        return {'allowed': False, 'reason': 'insufficient_headroom'}

    immediate = price_situation.get('immediate_action')
    if not immediate or immediate.get('action') != 'buy':
        return {'allowed': False, 'reason': 'no_immediate_buy'}

    return {'allowed': True, 'reason': 'ok'}


