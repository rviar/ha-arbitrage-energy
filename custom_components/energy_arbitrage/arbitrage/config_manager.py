"""
Centralized configuration management for energy arbitrage system.
Provides cached, consistent access to configuration values with type safety.
"""

import logging
from typing import Dict, Any, Optional, Union, Tuple
from functools import lru_cache
from dataclasses import dataclass
from ..const import (
    # Battery Configuration
    CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY,
    CONF_MIN_BATTERY_RESERVE, DEFAULT_MIN_BATTERY_RESERVE,
    CONF_BATTERY_EFFICIENCY, DEFAULT_BATTERY_EFFICIENCY,
    CONF_MAX_BATTERY_POWER, DEFAULT_MAX_BATTERY_POWER,
    CONF_BATTERY_COST, DEFAULT_BATTERY_COST,
    CONF_BATTERY_CYCLES, DEFAULT_BATTERY_CYCLES,
    CONF_DEGRADATION_FACTOR, DEFAULT_DEGRADATION_FACTOR,
    CONF_MAX_DAILY_CYCLES, DEFAULT_MAX_DAILY_CYCLES,
    CONF_MIN_ARBITRAGE_DEPTH, DEFAULT_MIN_ARBITRAGE_DEPTH,
    
    # System Configuration
    CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER,
    CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON,
    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL,
    CONF_MIN_ARBITRAGE_MARGIN, DEFAULT_MIN_ARBITRAGE_MARGIN,
    CONF_SELF_CONSUMPTION_PRIORITY, DEFAULT_SELF_CONSUMPTION_PRIORITY,
    CONF_INCLUDE_DEGRADATION, DEFAULT_INCLUDE_DEGRADATION,
    CONF_CURRENCY, DEFAULT_CURRENCY,
)
from .exceptions import ConfigurationError, safe_execute

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class BatterySpecs:
    """Battery specifications with validation."""
    capacity_wh: float
    min_reserve_percent: float
    efficiency_percent: float
    max_power_w: float
    cost: float
    rated_cycles: int
    degradation_factor: float
    max_daily_cycles: float
    min_arbitrage_depth_percent: float
    
    @property
    def usable_capacity_wh(self) -> float:
        """Usable capacity accounting for minimum reserve."""
        return self.capacity_wh * (100 - self.min_reserve_percent) / 100
    
    @property
    def arbitrage_capacity_wh(self) -> float:
        """Capacity available for arbitrage operations."""
        return self.capacity_wh * self.min_arbitrage_depth_percent / 100
    
    @property
    def efficiency_factor(self) -> float:
        """Efficiency as a factor (0-1)."""
        return self.efficiency_percent / 100


@dataclass(frozen=True)
class SystemSpecs:
    """System specifications with validation."""
    max_pv_power_w: float
    planning_horizon_hours: int
    update_interval_minutes: int
    currency: str
    self_consumption_priority: bool
    include_degradation: bool
    
    @property
    def update_interval_seconds(self) -> int:
        """Update interval in seconds."""
        return self.update_interval_minutes * 60


@dataclass(frozen=True)
class PriceThresholds:
    """Price and margin thresholds for arbitrage decisions."""
    min_arbitrage_margin_percent: float
    
    @property
    def min_margin_factor(self) -> float:
        """Minimum margin as a factor."""
        return self.min_arbitrage_margin_percent / 100


class ConfigManager:
    """
    Centralized configuration manager with caching and type safety.
    
    Provides consistent access to configuration values across the system
    while maintaining backward compatibility with existing config access patterns.
    """
    
    def __init__(self, entry_data: Dict[str, Any]):
        """
        Initialize with Home Assistant config entry data.
        
        Args:
            entry_data: Configuration data from Home Assistant config entry
        """
        self._entry_data = entry_data
        self._config_id = id(entry_data)  # For cache invalidation
    
    @safe_execute(default_return=None, raise_on_error=True)
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback to default.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self._entry_data.get(key, default)
    
    @lru_cache(maxsize=1)
    def get_battery_specs(self) -> BatterySpecs:
        """
        Get battery specifications with caching.
        
        Returns:
            BatterySpecs object with all battery-related configuration
        """
        return BatterySpecs(
            capacity_wh=self.get_config_value(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
            min_reserve_percent=self.get_config_value(CONF_MIN_BATTERY_RESERVE, DEFAULT_MIN_BATTERY_RESERVE),
            efficiency_percent=self.get_config_value(CONF_BATTERY_EFFICIENCY, DEFAULT_BATTERY_EFFICIENCY),
            max_power_w=self.get_config_value(CONF_MAX_BATTERY_POWER, DEFAULT_MAX_BATTERY_POWER),
            cost=self.get_config_value(CONF_BATTERY_COST, DEFAULT_BATTERY_COST),
            rated_cycles=self.get_config_value(CONF_BATTERY_CYCLES, DEFAULT_BATTERY_CYCLES),
            degradation_factor=self.get_config_value(CONF_DEGRADATION_FACTOR, DEFAULT_DEGRADATION_FACTOR),
            max_daily_cycles=self.get_config_value(CONF_MAX_DAILY_CYCLES, DEFAULT_MAX_DAILY_CYCLES),
            min_arbitrage_depth_percent=self.get_config_value(CONF_MIN_ARBITRAGE_DEPTH, DEFAULT_MIN_ARBITRAGE_DEPTH)
        )
    
    @lru_cache(maxsize=1)
    def get_system_specs(self) -> SystemSpecs:
        """
        Get system specifications with caching.
        
        Returns:
            SystemSpecs object with all system-related configuration
        """
        return SystemSpecs(
            max_pv_power_w=self.get_config_value(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER),
            planning_horizon_hours=self.get_config_value(CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON),
            update_interval_minutes=self.get_config_value(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            currency=self.get_config_value(CONF_CURRENCY, DEFAULT_CURRENCY),
            self_consumption_priority=self.get_config_value(CONF_SELF_CONSUMPTION_PRIORITY, DEFAULT_SELF_CONSUMPTION_PRIORITY),
            include_degradation=self.get_config_value(CONF_INCLUDE_DEGRADATION, DEFAULT_INCLUDE_DEGRADATION)
        )
    
    @lru_cache(maxsize=1)
    def get_price_thresholds(self) -> PriceThresholds:
        """
        Get price thresholds with caching.
        
        Returns:
            PriceThresholds object with pricing-related configuration
        """
        return PriceThresholds(
            min_arbitrage_margin_percent=self.get_config_value(CONF_MIN_ARBITRAGE_MARGIN, DEFAULT_MIN_ARBITRAGE_MARGIN)
        )
    
    @safe_execute(default_return={})
    def get_sensor_config(self) -> Dict[str, str]:
        """
        Get sensor entity IDs configuration.
        
        Returns:
            Dictionary mapping sensor types to entity IDs
        """
        from ..const import (
            CONF_PV_POWER_SENSOR, CONF_PV_FORECAST_TODAY_SENSOR,
            CONF_PV_FORECAST_TOMORROW_SENSOR, CONF_BATTERY_LEVEL_SENSOR,
            CONF_BATTERY_POWER_SENSOR, CONF_LOAD_POWER_SENSOR,
            CONF_GRID_POWER_SENSOR, CONF_TODAY_BATTERY_CYCLES_SENSOR,
            CONF_TOTAL_BATTERY_CYCLES_SENSOR
        )
        
        return {
            'pv_power': self.get_config_value(CONF_PV_POWER_SENSOR),
            'pv_forecast_today': self.get_config_value(CONF_PV_FORECAST_TODAY_SENSOR),
            'pv_forecast_tomorrow': self.get_config_value(CONF_PV_FORECAST_TOMORROW_SENSOR),
            'battery_level': self.get_config_value(CONF_BATTERY_LEVEL_SENSOR),
            'battery_power': self.get_config_value(CONF_BATTERY_POWER_SENSOR),
            'load_power': self.get_config_value(CONF_LOAD_POWER_SENSOR),
            'grid_power': self.get_config_value(CONF_GRID_POWER_SENSOR),
            'today_battery_cycles': self.get_config_value(CONF_TODAY_BATTERY_CYCLES_SENSOR),
            'total_battery_cycles': self.get_config_value(CONF_TOTAL_BATTERY_CYCLES_SENSOR)
        }
    
    @safe_execute(default_return={})
    def get_control_config(self) -> Dict[str, str]:
        """
        Get control entity IDs configuration.
        
        Returns:
            Dictionary mapping control types to entity IDs
        """
        from ..const import (
            CONF_WORK_MODE_SELECT, CONF_BATTERY_GRID_CHARGING_SWITCH,
            CONF_TIME_OF_USE_SELECT, CONF_EXPORT_SURPLUS_SWITCH
        )
        
        return {
            'work_mode_select': self.get_config_value(CONF_WORK_MODE_SELECT),
            'battery_grid_charging_switch': self.get_config_value(CONF_BATTERY_GRID_CHARGING_SWITCH),
            'time_of_use_select': self.get_config_value(CONF_TIME_OF_USE_SELECT),
            'export_surplus_switch': self.get_config_value(CONF_EXPORT_SURPLUS_SWITCH)
        }
    
    @safe_execute(default_return={})
    def get_mqtt_config(self) -> Dict[str, str]:
        """
        Get MQTT topic configuration.
        
        Returns:
            Dictionary mapping MQTT purposes to topic names
        """
        from ..const import CONF_MQTT_BUY_TOPIC, CONF_MQTT_SELL_TOPIC
        
        return {
            'buy_topic': self.get_config_value(CONF_MQTT_BUY_TOPIC),
            'sell_topic': self.get_config_value(CONF_MQTT_SELL_TOPIC)
        }
    
    def invalidate_cache(self):
        """Invalidate cached configuration values."""
        self.get_battery_specs.cache_clear()
        self.get_system_specs.cache_clear()
        self.get_price_thresholds.cache_clear()
    
    @property
    def entry_data(self) -> Dict[str, Any]:
        """Get raw entry data for backward compatibility."""
        return self._entry_data