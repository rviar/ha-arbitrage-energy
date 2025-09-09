"""
Energy Balance Predictor for predictive arbitrage decisions.
Analyzes PV forecasts, consumption patterns, and battery needs.
"""

import logging
from datetime import datetime, timezone, timedelta
from .utils import get_current_ha_time, get_ha_timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

@dataclass
class EnergyBalance:
    """Energy balance result for a specific period."""
    period: str                    # "today" | "tomorrow" | "next_24h"
    pv_forecast_wh: float         # Expected PV generation in Wh
    consumption_forecast_wh: float # Expected consumption in Wh
    net_balance_wh: float         # Net balance (+ surplus, - deficit)
    battery_needed_wh: float      # Battery energy needed to cover deficit
    confidence: float             # Forecast confidence 0-1
    
    @property
    def has_surplus(self) -> bool:
        """True if expected energy surplus."""
        return self.net_balance_wh > 0
    
    @property
    def has_deficit(self) -> bool:
        """True if expected energy deficit."""
        return self.net_balance_wh < 0
    
    @property
    def surplus_percentage(self) -> float:
        """Surplus as percentage of consumption."""
        if self.consumption_forecast_wh <= 0:
            return 0.0
        return max(0, self.net_balance_wh / self.consumption_forecast_wh * 100)
    
    @property
    def deficit_percentage(self) -> float:
        """Deficit as percentage of consumption."""
        if self.consumption_forecast_wh <= 0:
            return 0.0
        return max(0, -self.net_balance_wh / self.consumption_forecast_wh * 100)


class EnergyBalancePredictor:
    """Predicts energy balances and battery needs."""
    
    def __init__(self, sensor_helper):
        self.sensor_helper = sensor_helper
        self._consumption_history = []  # Will store historical data
        self._default_hourly_consumption = 750  # 750W average (18kWh/day)
        
    def calculate_energy_balance_today(self) -> EnergyBalance:
        """Calculate energy balance for remainder of today."""
        # FIXED: Use HA timezone instead of system timezone
        now = get_current_ha_time()
        
        # Get PV forecast for today
        pv_forecast_wh = self.sensor_helper.get_pv_forecast_today()
        pv_details = self.sensor_helper.get_pv_forecast_today_details()
        
        # Calculate remaining hours today
        hours_remaining = 24 - now.hour
        
        # Estimate remaining consumption today
        consumption_forecast_wh = self._estimate_consumption_remaining_today(now)
        
        # Calculate remaining PV forecast
        remaining_pv_wh = self._calculate_remaining_pv_today(pv_forecast_wh, pv_details, now)
        
        net_balance = remaining_pv_wh - consumption_forecast_wh
        battery_needed = max(0, -net_balance)
        
        return EnergyBalance(
            period="today_remaining",
            pv_forecast_wh=remaining_pv_wh,
            consumption_forecast_wh=consumption_forecast_wh,
            net_balance_wh=net_balance,
            battery_needed_wh=battery_needed,
            confidence=0.8  # High confidence for current day
        )
    
    def calculate_energy_balance_tomorrow(self) -> EnergyBalance:
        """Calculate energy balance for tomorrow."""
        
        # Get PV forecast for tomorrow
        pv_forecast_wh = self.sensor_helper.get_pv_forecast_tomorrow()
        
        # Estimate full day consumption (24 hours)
        consumption_forecast_wh = self._estimate_daily_consumption()
        
        net_balance = pv_forecast_wh - consumption_forecast_wh
        battery_needed = max(0, -net_balance)
        
        return EnergyBalance(
            period="tomorrow",
            pv_forecast_wh=pv_forecast_wh,
            consumption_forecast_wh=consumption_forecast_wh,
            net_balance_wh=net_balance,
            battery_needed_wh=battery_needed,
            confidence=0.7  # Medium confidence for next day
        )
    
    def calculate_combined_balance(self) -> Dict[str, EnergyBalance]:
        """Calculate energy balances for multiple periods."""
        
        today_balance = self.calculate_energy_balance_today()
        tomorrow_balance = self.calculate_energy_balance_tomorrow()
        
        # Calculate 48-hour outlook
        total_pv = today_balance.pv_forecast_wh + tomorrow_balance.pv_forecast_wh
        total_consumption = today_balance.consumption_forecast_wh + tomorrow_balance.consumption_forecast_wh
        
        combined_balance = EnergyBalance(
            period="next_48h",
            pv_forecast_wh=total_pv,
            consumption_forecast_wh=total_consumption,
            net_balance_wh=total_pv - total_consumption,
            battery_needed_wh=max(0, total_consumption - total_pv),
            confidence=0.6  # Lower confidence for longer period
        )
        
        return {
            'today': today_balance,
            'tomorrow': tomorrow_balance,
            'next_48h': combined_balance
        }
    
    def assess_battery_strategy(self, current_battery_level: float, battery_capacity_wh: float) -> Dict[str, Any]:
        """Assess optimal battery strategy based on energy forecasts."""
        
        balances = self.calculate_combined_balance()
        current_battery_wh = (current_battery_level / 100) * battery_capacity_wh
        
        today = balances['today']
        tomorrow = balances['tomorrow']
        
        strategy = {
            'recommendation': 'hold',
            'reason': '',
            'target_battery_level': current_battery_level,
            'urgency': 'low',  # low/medium/high
            'confidence': min(today.confidence, tomorrow.confidence)
        }
        
        # Strategy logic
        if today.has_deficit and tomorrow.has_deficit:
            # Both days need battery
            needed_energy = today.battery_needed_wh + tomorrow.battery_needed_wh * 0.5  # Discount tomorrow
            if current_battery_wh < needed_energy:
                strategy.update({
                    'recommendation': 'charge_aggressive',
                    'reason': f'Both days need battery. Deficit today: {today.deficit_percentage:.0f}%, tomorrow: {tomorrow.deficit_percentage:.0f}%',
                    'target_battery_level': min(95, (needed_energy / battery_capacity_wh) * 100 + 20),
                    'urgency': 'high'
                })
        
        elif today.has_deficit and tomorrow.has_surplus:
            # Today deficit, tomorrow surplus
            if current_battery_wh < today.battery_needed_wh:
                strategy.update({
                    'recommendation': 'charge_moderate',
                    'reason': f'Today needs battery ({today.deficit_percentage:.0f}%), tomorrow surplus ({tomorrow.surplus_percentage:.0f}%)',
                    'target_battery_level': min(70, (today.battery_needed_wh / battery_capacity_wh) * 100 + 15),
                    'urgency': 'medium'
                })
        
        elif today.has_surplus and tomorrow.has_deficit:
            # Today surplus, tomorrow deficit  
            if current_battery_level > 80:
                strategy.update({
                    'recommendation': 'sell_partial',
                    'reason': f'Today surplus ({today.surplus_percentage:.0f}%), tomorrow deficit ({tomorrow.deficit_percentage:.0f}%). Reserve for tomorrow.',
                    'target_battery_level': max(60, (tomorrow.battery_needed_wh / battery_capacity_wh) * 100 + 20),
                    'urgency': 'low'
                })
        
        elif today.has_surplus and tomorrow.has_surplus:
            # Both days surplus
            if current_battery_level > 60:
                strategy.update({
                    'recommendation': 'sell_aggressive',
                    'reason': f'Both days surplus. Today: {today.surplus_percentage:.0f}%, tomorrow: {tomorrow.surplus_percentage:.0f}%',
                    'target_battery_level': 40,
                    'urgency': 'low'
                })
        
        return strategy
    
    def _estimate_consumption_remaining_today(self, now: datetime) -> float:
        """Estimate consumption for remainder of today."""
        hours_remaining = 24 - now.hour
        
        # Simple model: higher consumption in evening hours
        hourly_patterns = {
            0: 0.6, 1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.6,
            6: 0.8, 7: 1.2, 8: 1.0, 9: 0.8, 10: 0.7, 11: 0.8,
            12: 0.9, 13: 0.8, 14: 0.7, 15: 0.8, 16: 1.0, 17: 1.3,
            18: 1.5, 19: 1.4, 20: 1.2, 21: 1.0, 22: 0.9, 23: 0.7
        }
        
        total_consumption = 0
        for hour in range(now.hour, 24):
            hourly_consumption = self._default_hourly_consumption * hourly_patterns.get(hour, 1.0)
            total_consumption += hourly_consumption
        
        return total_consumption
    
    def _estimate_daily_consumption(self) -> float:
        """Estimate consumption for full day."""
        # Simple model: 18 kWh per day average
        return 18000  # Wh
    
    def _calculate_remaining_pv_today(self, total_pv_wh: float, pv_details: Dict, now: datetime) -> float:
        """Calculate remaining PV generation for today."""
        if not pv_details or 'forecasts' not in pv_details:
            # Fallback: assume PV generation follows sun pattern
            sunset_hour = 20  # Approximate
            if now.hour >= sunset_hour:
                return 0
            
            # Simple model: most PV in middle of day
            remaining_ratio = max(0, (sunset_hour - now.hour) / 12)  # Rough approximation
            return total_pv_wh * remaining_ratio
        
        # Use detailed forecast data if available
        # (Implementation depends on Solcast data structure)
        # For now, use simple fallback
        current_hour = now.hour
        if current_hour >= 20:  # After sunset
            return 0
        elif current_hour <= 6:  # Before sunrise
            return total_pv_wh
        else:  # During day
            hours_of_sun_remaining = max(0, 20 - current_hour)
            return total_pv_wh * (hours_of_sun_remaining / 14)  # 14 hours of daylight
    
    def get_energy_situation_summary(self) -> str:
        """Get human-readable summary of energy situation."""
        balances = self.calculate_combined_balance()
        
        today = balances['today']
        tomorrow = balances['tomorrow']
        
        if today.has_surplus and tomorrow.has_surplus:
            return f"abundant_energy"  # Много энергии оба дня
        elif today.has_deficit and tomorrow.has_deficit:
            return f"energy_shortage"  # Дефицит энергии оба дня  
        elif today.has_surplus and tomorrow.has_deficit:
            return f"surplus_today_deficit_tomorrow"
        elif today.has_deficit and tomorrow.has_surplus:
            return f"deficit_today_surplus_tomorrow"
        else:
            return f"balanced_energy"
