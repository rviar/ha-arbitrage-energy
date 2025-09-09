"""
Home Assistant entities for Peak Detection configuration and monitoring.
Provides user interface for peak detection system through HA entities.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PeakDetectionEnableSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable peak detection system."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_detection_enabled"
        self._attr_name = "Peak Detection Enabled"
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_entity_category = EntityCategory.CONFIG
        
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Energy Arbitrage Peak Detection",
            "manufacturer": "Energy Arbitrage",
            "model": "Peak Detection System",
            "via_device": (DOMAIN, self.entry.entry_id),
        }
    
    @property
    def is_on(self) -> bool:
        """Return true if peak detection is enabled."""
        if not self.coordinator.data:
            return True  # Default enabled
        
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return options.get('peak_detection_enabled', config.get('peak_detection_enabled', True))
    
    async def async_turn_on(self, **kwargs):
        """Enable peak detection."""
        options = dict(self.entry.options)
        options['peak_detection_enabled'] = True
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Peak detection enabled")
    
    async def async_turn_off(self, **kwargs):
        """Disable peak detection.""" 
        options = dict(self.entry.options)
        options['peak_detection_enabled'] = False
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Peak detection disabled")

class PeakDetectionZScoreThreshold(CoordinatorEntity, NumberEntity):
    """Number entity for Z-score threshold configuration."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_z_score_threshold"
        self._attr_name = "Peak Z-Score Threshold"
        self._attr_icon = "mdi:chart-bell-curve-cumulative"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 1.0
        self._attr_native_max_value = 3.0
        self._attr_native_step = 0.1
        self._attr_native_unit_of_measurement = "σ"
        self._attr_mode = "slider"
        
    @property
    def native_value(self) -> float:
        """Return current Z-score threshold."""
        if not self.coordinator.data:
            return 1.5
            
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return options.get('peak_detection_z_threshold', config.get('peak_detection_z_threshold', 1.5))
    
    async def async_set_native_value(self, value: float):
        """Set Z-score threshold."""
        options = dict(self.entry.options)
        options['peak_detection_z_threshold'] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info(f"Peak Z-score threshold set to {value}")

class PeakDetectionStrategicMultiplier(CoordinatorEntity, NumberEntity):
    """Number entity for strategic override multiplier."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_strategic_multiplier"
        self._attr_name = "Strategic Override Multiplier"
        self._attr_icon = "mdi:multiplication"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 1.05
        self._attr_native_max_value = 1.50
        self._attr_native_step = 0.01
        self._attr_native_unit_of_measurement = "x"
        self._attr_mode = "box"
        
    @property
    def native_value(self) -> float:
        """Return current strategic override multiplier."""
        if not self.coordinator.data:
            return 1.10
            
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return options.get('peak_detection_strategic_multiplier', config.get('peak_detection_strategic_multiplier', 1.10))
    
    async def async_set_native_value(self, value: float):
        """Set strategic override multiplier."""
        options = dict(self.entry.options)
        options['peak_detection_strategic_multiplier'] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info(f"Strategic override multiplier set to {value}")

class PeakDetectionExtremeMultiplier(CoordinatorEntity, NumberEntity):
    """Number entity for extreme peak multiplier."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_extreme_multiplier"
        self._attr_name = "Extreme Peak Multiplier"
        self._attr_icon = "mdi:trending-up"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 1.10
        self._attr_native_max_value = 1.50
        self._attr_native_step = 0.01
        self._attr_native_unit_of_measurement = "x"
        self._attr_mode = "box"
        
    @property
    def native_value(self) -> float:
        """Return current extreme peak multiplier."""
        if not self.coordinator.data:
            return 1.20
            
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return options.get('peak_detection_extreme_multiplier', config.get('peak_detection_extreme_multiplier', 1.20))
    
    async def async_set_native_value(self, value: float):
        """Set extreme peak multiplier."""
        options = dict(self.entry.options)
        options['peak_detection_extreme_multiplier'] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info(f"Extreme peak multiplier set to {value}")

class PeakDetectionLookbackHours(CoordinatorEntity, NumberEntity):
    """Number entity for historical lookback period."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_lookback_hours"
        self._attr_name = "Peak Detection Lookback Hours"
        self._attr_icon = "mdi:clock-time-four-outline"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 12
        self._attr_native_max_value = 48
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "h"
        self._attr_mode = "box"
        
    @property
    def native_value(self) -> int:
        """Return current lookback hours."""
        if not self.coordinator.data:
            return 24
            
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return int(options.get('peak_detection_lookback_hours', config.get('peak_detection_lookback_hours', 24)))
    
    async def async_set_native_value(self, value: float):
        """Set lookback hours."""
        options = dict(self.entry.options)
        options['peak_detection_lookback_hours'] = int(value)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info(f"Peak detection lookback hours set to {int(value)}")

class PeakDetectionMaxPowerPercent(CoordinatorEntity, NumberEntity):
    """Number entity for maximum peak power percentage."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_max_power_percent"
        self._attr_name = "Peak Max Power Percentage"
        self._attr_icon = "mdi:battery-charging-100"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 50
        self._attr_native_max_value = 100
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = "slider"
        
    @property
    def native_value(self) -> int:
        """Return current max power percentage."""
        if not self.coordinator.data:
            return 90
            
        options = self.coordinator.data.get('options', {})
        config = self.coordinator.data.get('config', {})
        return int(options.get('peak_detection_max_power_percent', config.get('peak_detection_max_power_percent', 90)))
    
    async def async_set_native_value(self, value: float):
        """Set max power percentage."""
        options = dict(self.entry.options)
        options['peak_detection_max_power_percent'] = int(value)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.coordinator.async_request_refresh()
        _LOGGER.info(f"Peak detection max power percentage set to {int(value)}%")

class PeakDetectionStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing peak detection system status."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_detection_status"
        self._attr_name = "Peak Detection Status"
        self._attr_icon = "mdi:radar"
        
    @property
    def native_value(self) -> str:
        """Return peak detection status."""
        if not hasattr(self.coordinator, 'optimizer') or not self.coordinator.optimizer:
            return "inactive"
        
        peak_detector = getattr(self.coordinator.optimizer, 'peak_detector', None)
        if not peak_detector:
            return "unavailable"
        
        if not peak_detector.is_enabled():
            return "disabled"
        
        # Check recent activity
        stats = peak_detector.get_peak_statistics()
        if stats.get('last_peak_time'):
            try:
                last_peak = datetime.fromisoformat(stats['last_peak_time'].replace('Z', '+00:00'))
                time_since_peak = (datetime.now().astimezone() - last_peak).total_seconds() / 3600
                if time_since_peak < 1:
                    return "active_peak_detected"
                elif time_since_peak < 6:
                    return "monitoring_recent_activity"
            except (ValueError, TypeError):
                pass
        
        return "monitoring"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional status attributes."""
        if not hasattr(self.coordinator, 'optimizer') or not self.coordinator.optimizer:
            return {}
        
        peak_detector = getattr(self.coordinator.optimizer, 'peak_detector', None)
        if not peak_detector:
            return {}
        
        stats = peak_detector.get_peak_statistics()
        
        # Get configuration
        enabled = peak_detector.is_enabled()
        
        attributes = {
            "enabled": enabled,
            "total_peaks_detected": stats.get('total_peaks_detected', 0),
            "overrides_triggered": stats.get('overrides_triggered', 0),
            "average_confidence": stats.get('average_confidence', 0.0),
            "last_peak_time": stats.get('last_peak_time', None),
            "analysis_history_size": stats.get('analysis_history_size', 0),
            "price_history_size": stats.get('price_history_size', 0)
        }
        
        # Add peak type counts
        peak_types = stats.get('peak_types_count', {})
        for peak_type, count in peak_types.items():
            attributes[f"{peak_type}_count"] = count
        
        return attributes

class PeakDetectionStatisticsSensor(CoordinatorEntity, SensorEntity):
    """Sensor with detailed peak detection statistics."""
    
    def __init__(self, coordinator, entry, **kwargs):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_detection_statistics"
        self._attr_name = "Peak Detection Statistics"
        self._attr_icon = "mdi:chart-line"
        self._attr_native_unit_of_measurement = "peaks"
        
    @property
    def native_value(self) -> int:
        """Return total number of peaks detected."""
        if not hasattr(self.coordinator, 'optimizer') or not self.coordinator.optimizer:
            return 0
        
        peak_detector = getattr(self.coordinator.optimizer, 'peak_detector', None)
        if not peak_detector:
            return 0
        
        stats = peak_detector.get_peak_statistics()
        return stats.get('total_peaks_detected', 0)
    
    @property  
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return detailed statistics."""
        if not hasattr(self.coordinator, 'optimizer') or not self.coordinator.optimizer:
            return {}
        
        peak_detector = getattr(self.coordinator.optimizer, 'peak_detector', None)
        peak_handler = getattr(self.coordinator.optimizer, 'peak_override_handler', None)
        
        if not peak_detector:
            return {}
        
        stats = peak_detector.get_peak_statistics()
        attributes = dict(stats)
        
        # Add handler status if available
        if peak_handler:
            handler_status = peak_handler.get_handler_status()
            attributes.update({
                "handler_priority": handler_status.get('priority'),
                "last_action_time": handler_status.get('last_action_time')
            })
        
        # Add configuration summary
        if peak_detector.is_enabled():
            attributes.update({
                "z_score_threshold": peak_detector._get_configuration('peak_detection_z_threshold', 1.5),
                "strategic_multiplier": peak_detector._get_configuration('peak_detection_strategic_multiplier', 1.10),
                "extreme_multiplier": peak_detector._get_configuration('peak_detection_extreme_multiplier', 1.20),
                "lookback_hours": peak_detector._get_configuration('peak_detection_lookback_hours', 24)
            })
        
        return attributes