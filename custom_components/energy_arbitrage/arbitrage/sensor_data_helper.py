"""
Helper class for accessing sensor data in the arbitrage algorithm.
This ensures all data is accessed through sensors rather than direct config/entity access.
"""

import logging
from typing import Any, Optional, Dict
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class SensorDataHelper:
    """Helper class to access sensor data for arbitrage calculations."""
    
    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator=None):
        self.hass = hass
        self.entry_id = entry_id
        self.domain = "energy_arbitrage"
        self.coordinator = coordinator
    
    def _get_sensor_value(self, sensor_suffix: str) -> Optional[float]:
        """Get value from a sensor by its suffix."""
        entity_id = f"sensor.{self.domain}_{sensor_suffix}"
        state = self.hass.states.get(entity_id)
        
        if state is None:
            _LOGGER.warning(f"Sensor {entity_id} not found")
            return None
        
        try:
            return float(state.state)
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"Cannot convert sensor {entity_id} value '{state.state}' to float: {e}")
            return None
    
    def _get_sensor_attributes(self, sensor_suffix: str) -> Dict[str, Any]:
        """Get attributes from a sensor by its suffix."""
        entity_id = f"sensor.{self.domain}_{sensor_suffix}"
        state = self.hass.states.get(entity_id)
        
        if state is None:
            _LOGGER.warning(f"Sensor {entity_id} not found")
            return {}
        
        return dict(state.attributes)
    
    # Input Data Sensors
    
    def get_current_buy_price(self) -> float:
        """Get current electricity buy price."""
        return self._get_sensor_value("current_buy_price") or 0.0
    
    def get_current_sell_price(self) -> float:
        """Get current electricity sell price."""
        return self._get_sensor_value("current_sell_price") or 0.0
    
    def get_min_buy_price_24h(self) -> float:
        """Get minimum buy price in next 24h."""
        return self._get_sensor_value("min_buy_price_24h") or 0.0
    
    def get_max_sell_price_24h(self) -> float:
        """Get maximum sell price in next 24h."""
        return self._get_sensor_value("max_sell_price_24h") or 0.0
    
    def get_battery_level(self) -> float:
        """Get current battery level in %."""
        return self._get_sensor_value("input_battery_level") or 0.0
    
    def get_pv_power(self) -> float:
        """Get current PV power in W."""
        return self._get_sensor_value("input_pv_power") or 0.0
    
    def get_load_power(self) -> float:
        """Get current load power in W."""
        return self._get_sensor_value("input_load_power") or 0.0
    
    def get_grid_power(self) -> float:
        """Get current grid power in W."""
        return self._get_sensor_value("input_grid_power") or 0.0
    
    def get_pv_forecast_today(self) -> float:
        """Get PV forecast for today in Wh."""
        return self._get_sensor_value("input_pv_forecast_today") or 0.0
    
    def get_pv_forecast_today_details(self) -> Dict[str, Any]:
        """Get detailed PV forecast for today."""
        return self._get_sensor_attributes("input_pv_forecast_today")
    
    def get_pv_forecast_tomorrow(self) -> float:
        """Get PV forecast for tomorrow in Wh."""
        return self._get_sensor_value("input_pv_forecast_tomorrow") or 0.0
    
    def get_pv_forecast_tomorrow_details(self) -> Dict[str, Any]:
        """Get detailed PV forecast for tomorrow."""
        return self._get_sensor_attributes("input_pv_forecast_tomorrow")
    
    def get_available_battery_capacity(self) -> float:
        """Get available battery capacity above reserve in Wh."""
        return self._get_sensor_value("available_battery_capacity") or 0.0
    
    def get_net_consumption(self) -> float:
        """Get net consumption (Load - PV) in W."""
        return self._get_sensor_value("net_consumption") or 0.0
    
    def get_surplus_power(self) -> float:
        """Get surplus power (PV - Load) in W."""
        return self._get_sensor_value("surplus_power") or 0.0
    
    # Configuration Parameter from Number Entities
    
    def _get_number_value(self, number_suffix: str) -> Optional[float]:
        """Get value from a number entity by its suffix."""
        entity_id = f"number.{self.domain}_{number_suffix}"
        state = self.hass.states.get(entity_id)
        
        if state is None:
            _LOGGER.warning(f"Number entity {entity_id} not found")
            return None
        
        try:
            return float(state.state)
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"Cannot convert number entity {entity_id} value '{state.state}' to float: {e}")
            return None
    
    def get_min_arbitrage_margin(self) -> float:
        """Get minimum arbitrage margin in %."""
        return self._get_number_value("min_arbitrage_margin") or 5.0
    
    def get_planning_horizon(self) -> int:
        """Get planning horizon in hours."""
        value = self._get_number_value("planning_horizon")
        return int(value) if value is not None else 24
    
    def get_max_daily_cycles(self) -> float:
        """Get maximum daily battery cycles."""
        return self._get_number_value("max_daily_cycles") or 2.0
    
    def get_battery_efficiency(self) -> float:
        """Get battery efficiency in % (returns as decimal 0-1) from coordinator data."""
        if self.coordinator and self.coordinator.data:
            value = self.coordinator.data.get("battery_efficiency", 90.0)
            return value / 100.0
        return 0.9
    
    def get_min_battery_reserve(self) -> float:
        """Get minimum battery reserve in % from coordinator data."""
        if self.coordinator and self.coordinator.data:
            return self.coordinator.data.get("min_battery_reserve", 20.0)
        return 20.0
    
    def get_max_battery_power(self) -> float:
        """Get maximum battery power in W from coordinator data."""
        if self.coordinator and self.coordinator.data:
            return self.coordinator.data.get("max_battery_power", 5000.0)
        return 5000.0
    
    def get_battery_capacity(self) -> float:
        """Get battery capacity in Wh from coordinator data."""
        if self.coordinator and self.coordinator.data:
            return self.coordinator.data.get("battery_capacity", 15000)
        return 15000
    
    # Derived calculations
    
    def get_current_price_spread(self) -> float:
        """Get current price spread (sell - buy)."""
        return self.get_current_sell_price() - self.get_current_buy_price()
    
    def get_max_arbitrage_potential(self) -> float:
        """Get maximum arbitrage potential in next 24h."""
        return self.get_max_sell_price_24h() - self.get_min_buy_price_24h()
    
    def is_battery_charging_viable(self) -> bool:
        """Check if battery has room for charging."""
        battery_level = self.get_battery_level()
        return battery_level < 95.0
    
    def is_battery_discharging_viable(self) -> bool:
        """Check if battery can be discharged (above reserve)."""
        battery_level = self.get_battery_level()
        min_reserve = self.get_min_battery_reserve()
        return battery_level > min_reserve + 10.0  # 10% buffer above reserve
    
    def get_arbitrage_roi(self, buy_price: float, sell_price: float, kwh: float = 1.0) -> float:
        """Calculate ROI for arbitrage opportunity."""
        if buy_price <= 0:
            return 0.0
        
        efficiency = self.get_battery_efficiency()
        gross_profit = sell_price - buy_price
        net_profit = gross_profit * efficiency * kwh
        roi = (net_profit / (buy_price * kwh)) * 100
        
        return max(0.0, roi)
    
    def get_current_state_summary(self) -> Dict[str, Any]:
        """Get summary of current system state from sensors."""
        return {
            # Current measurements
            "battery_level": self.get_battery_level(),
            "pv_power": self.get_pv_power(),
            "load_power": self.get_load_power(),
            "grid_power": self.get_grid_power(),
            "net_consumption": self.get_net_consumption(),
            "surplus_power": self.get_surplus_power(),
            "available_battery_capacity": self.get_available_battery_capacity(),
            
            # Price information
            "current_buy_price": self.get_current_buy_price(),
            "current_sell_price": self.get_current_sell_price(),
            "min_buy_price_24h": self.get_min_buy_price_24h(),
            "max_sell_price_24h": self.get_max_sell_price_24h(),
            "current_price_spread": self.get_current_price_spread(),
            "max_arbitrage_potential": self.get_max_arbitrage_potential(),
            
            # Configuration
            "min_arbitrage_margin": self.get_min_arbitrage_margin(),
            "planning_horizon": self.get_planning_horizon(),
            "max_daily_cycles": self.get_max_daily_cycles(),
            "battery_efficiency": self.get_battery_efficiency(),
            "min_battery_reserve": self.get_min_battery_reserve(),
            "max_battery_power": self.get_max_battery_power(),
            "battery_capacity": self.get_battery_capacity(),
            
            # Status flags
            "can_charge": self.is_battery_charging_viable(),
            "can_discharge": self.is_battery_discharging_viable(),
        }
    
    def log_current_state(self):
        """Log current system state for debugging."""
        state = self.get_current_state_summary()
        
        _LOGGER.info(
            f"Current state: Battery {state['battery_level']:.1f}%, "
            f"PV {state['pv_power']:.0f}W, Load {state['load_power']:.0f}W, "
            f"Grid {state['grid_power']:.0f}W"
        )
        
        _LOGGER.info(
            f"Prices: Buy {state['current_buy_price']:.4f}, "
            f"Sell {state['current_sell_price']:.4f}, "
            f"Spread {state['current_price_spread']:.4f}"
        )
        
        _LOGGER.info(
            f"Config: Min margin {state['min_arbitrage_margin']:.1f}%, "
            f"Battery {state['battery_capacity']:.0f}Wh @ {state['battery_efficiency']*100:.0f}%, "
            f"Reserve {state['min_battery_reserve']:.0f}%"
        )