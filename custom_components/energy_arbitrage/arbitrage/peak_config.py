"""
Peak Detection Configuration Management
Provides dynamic configuration for ExceptionalPeakDetector with HA entity integration.
"""

import logging
from typing import Dict, Any, Optional
from ..const import DOMAIN
from .peak_detector import PeakDetectionConfig

_LOGGER = logging.getLogger(__name__)

class PeakConfigManager:
    """Manages peak detection configuration with Home Assistant entity integration."""
    
    # Peak Detection Configuration Constants
    CONF_ENABLE_PEAK_DETECTION = "enable_peak_detection"
    CONF_STATISTICAL_THRESHOLD = "statistical_threshold" 
    CONF_STRATEGIC_OVERRIDE_MULTIPLIER = "strategic_override_multiplier"
    CONF_EXTREME_PEAK_MULTIPLIER = "extreme_peak_multiplier"
    CONF_ROLLING_WINDOW_HOURS = "rolling_window_hours"
    CONF_MIN_HISTORICAL_POINTS = "min_historical_points"
    CONF_DETECTION_INTERVAL_SEC = "detection_interval_sec"
    CONF_ENABLE_STATISTICAL_DETECTION = "enable_statistical_detection"
    CONF_ENABLE_STRATEGIC_OVERRIDE = "enable_strategic_override"
    CONF_ENABLE_EXTREME_PEAK_BOOST = "enable_extreme_peak_boost"
    CONF_ENABLE_REAL_TIME_ALERTS = "enable_real_time_alerts"
    
    # Default Values
    DEFAULT_ENABLE_PEAK_DETECTION = True
    DEFAULT_STATISTICAL_THRESHOLD = 1.5
    DEFAULT_STRATEGIC_OVERRIDE_MULTIPLIER = 1.10
    DEFAULT_EXTREME_PEAK_MULTIPLIER = 1.20
    DEFAULT_ROLLING_WINDOW_HOURS = 24
    DEFAULT_MIN_HISTORICAL_POINTS = 12
    DEFAULT_DETECTION_INTERVAL_SEC = 60
    DEFAULT_ENABLE_STATISTICAL_DETECTION = True
    DEFAULT_ENABLE_STRATEGIC_OVERRIDE = True
    DEFAULT_ENABLE_EXTREME_PEAK_BOOST = True
    DEFAULT_ENABLE_REAL_TIME_ALERTS = True
    
    def __init__(self, hass, entry_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self._cached_config = None
        self._last_update = None
        
    def get_peak_detection_config(self, options: Optional[Dict[str, Any]] = None, 
                                 config: Optional[Dict[str, Any]] = None) -> PeakDetectionConfig:
        """Get current peak detection configuration from HA entities or fallback to defaults."""
        
        # Try to get from HA entities first (live configuration)
        entity_config = self._get_config_from_entities()
        
        # Merge with options and config (in priority order: entities > options > config > defaults)
        merged_config = self._merge_config_sources(entity_config, options, config)
        
        return PeakDetectionConfig(
            statistical_threshold=merged_config.get(
                self.CONF_STATISTICAL_THRESHOLD, 
                self.DEFAULT_STATISTICAL_THRESHOLD
            ),
            rolling_window_hours=merged_config.get(
                self.CONF_ROLLING_WINDOW_HOURS,
                self.DEFAULT_ROLLING_WINDOW_HOURS
            ),
            min_historical_points=merged_config.get(
                self.CONF_MIN_HISTORICAL_POINTS,
                self.DEFAULT_MIN_HISTORICAL_POINTS
            ),
            strategic_override_multiplier=merged_config.get(
                self.CONF_STRATEGIC_OVERRIDE_MULTIPLIER,
                self.DEFAULT_STRATEGIC_OVERRIDE_MULTIPLIER
            ),
            extreme_peak_multiplier=merged_config.get(
                self.CONF_EXTREME_PEAK_MULTIPLIER,
                self.DEFAULT_EXTREME_PEAK_MULTIPLIER
            ),
            detection_interval_sec=merged_config.get(
                self.CONF_DETECTION_INTERVAL_SEC,
                self.DEFAULT_DETECTION_INTERVAL_SEC
            ),
            enable_statistical_detection=merged_config.get(
                self.CONF_ENABLE_STATISTICAL_DETECTION,
                self.DEFAULT_ENABLE_STATISTICAL_DETECTION
            ),
            enable_strategic_override=merged_config.get(
                self.CONF_ENABLE_STRATEGIC_OVERRIDE,
                self.DEFAULT_ENABLE_STRATEGIC_OVERRIDE
            ),
            enable_extreme_peak_boost=merged_config.get(
                self.CONF_ENABLE_EXTREME_PEAK_BOOST,
                self.DEFAULT_ENABLE_EXTREME_PEAK_BOOST
            ),
            enable_real_time_alerts=merged_config.get(
                self.CONF_ENABLE_REAL_TIME_ALERTS,
                self.DEFAULT_ENABLE_REAL_TIME_ALERTS
            )
        )
    
    def _get_config_from_entities(self) -> Dict[str, Any]:
        """Get peak detection configuration from Home Assistant entities."""
        entity_config = {}
        
        # Define entity mappings
        entity_mappings = {
            f"switch.{DOMAIN}_enable_peak_detection": (self.CONF_ENABLE_PEAK_DETECTION, bool),
            f"number.{DOMAIN}_statistical_threshold": (self.CONF_STATISTICAL_THRESHOLD, float),
            f"number.{DOMAIN}_strategic_override_multiplier": (self.CONF_STRATEGIC_OVERRIDE_MULTIPLIER, float),
            f"number.{DOMAIN}_extreme_peak_multiplier": (self.CONF_EXTREME_PEAK_MULTIPLIER, float),
            f"number.{DOMAIN}_rolling_window_hours": (self.CONF_ROLLING_WINDOW_HOURS, int),
            f"number.{DOMAIN}_min_historical_points": (self.CONF_MIN_HISTORICAL_POINTS, int),
            f"number.{DOMAIN}_detection_interval_sec": (self.CONF_DETECTION_INTERVAL_SEC, int),
            f"switch.{DOMAIN}_enable_statistical_detection": (self.CONF_ENABLE_STATISTICAL_DETECTION, bool),
            f"switch.{DOMAIN}_enable_strategic_override": (self.CONF_ENABLE_STRATEGIC_OVERRIDE, bool),
            f"switch.{DOMAIN}_enable_extreme_peak_boost": (self.CONF_ENABLE_EXTREME_PEAK_BOOST, bool),
            f"switch.{DOMAIN}_enable_real_time_alerts": (self.CONF_ENABLE_REAL_TIME_ALERTS, bool),
        }
        
        for entity_id, (config_key, value_type) in entity_mappings.items():
            try:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ['unknown', 'unavailable']:
                    if value_type == bool:
                        entity_config[config_key] = state.state.lower() in ['on', 'true']
                    elif value_type == float:
                        entity_config[config_key] = float(state.state)
                    elif value_type == int:
                        entity_config[config_key] = int(float(state.state))  # Handle decimal inputs
                        
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Failed to parse {entity_id}: {e}")
                continue
        
        _LOGGER.debug(f"🔬 Peak config from entities: {entity_config}")
        return entity_config
    
    def _merge_config_sources(self, entity_config: Dict[str, Any], 
                            options: Optional[Dict[str, Any]], 
                            config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge configuration from multiple sources in priority order."""
        merged = {}
        
        # Start with defaults, then config, then options, then entities (highest priority)
        sources = [config or {}, options or {}, entity_config]
        
        for source in sources:
            if source:
                merged.update(source)
        
        return merged
    
    def is_peak_detection_enabled(self, options: Optional[Dict[str, Any]] = None, 
                                 config: Optional[Dict[str, Any]] = None) -> bool:
        """Check if peak detection is enabled."""
        entity_config = self._get_config_from_entities()
        merged = self._merge_config_sources(entity_config, options, config)
        
        return merged.get(self.CONF_ENABLE_PEAK_DETECTION, self.DEFAULT_ENABLE_PEAK_DETECTION)
    
    def get_entity_definitions(self) -> List[Dict[str, Any]]:
        """Get entity definitions for creating HA entities."""
        return [
            # Main enable/disable switch
            {
                "type": "switch",
                "key": "enable_peak_detection", 
                "name": "Enable Peak Detection",
                "default": self.DEFAULT_ENABLE_PEAK_DETECTION,
                "icon": "mdi:lightning-bolt-outline",
                "category": "config"
            },
            
            # Core thresholds
            {
                "type": "number",
                "key": "statistical_threshold",
                "name": "Statistical Threshold",
                "default": self.DEFAULT_STATISTICAL_THRESHOLD,
                "min": 1.0,
                "max": 5.0,
                "step": 0.1,
                "unit": "σ",
                "icon": "mdi:chart-bell-curve-cumulative",
                "category": "config"
            },
            {
                "type": "number",
                "key": "strategic_override_multiplier",
                "name": "Strategic Override Multiplier",
                "default": self.DEFAULT_STRATEGIC_OVERRIDE_MULTIPLIER,
                "min": 1.05,
                "max": 2.0,
                "step": 0.05,
                "unit": "x",
                "icon": "mdi:strategy",
                "category": "config"  
            },
            {
                "type": "number",
                "key": "extreme_peak_multiplier",
                "name": "Extreme Peak Multiplier",
                "default": self.DEFAULT_EXTREME_PEAK_MULTIPLIER,
                "min": 1.10,
                "max": 3.0,
                "step": 0.10,
                "unit": "x",
                "icon": "mdi:alert-octagram-outline",
                "category": "config"
            },
            
            # Historical data settings
            {
                "type": "number", 
                "key": "rolling_window_hours",
                "name": "Historical Window Hours",
                "default": self.DEFAULT_ROLLING_WINDOW_HOURS,
                "min": 6,
                "max": 168,  # 1 week
                "step": 1,
                "unit": "h",
                "icon": "mdi:clock-time-eight-outline",
                "category": "config"
            },
            {
                "type": "number",
                "key": "min_historical_points", 
                "name": "Minimum Historical Points",
                "default": self.DEFAULT_MIN_HISTORICAL_POINTS,
                "min": 6,
                "max": 100,
                "step": 1,
                "unit": "points",
                "icon": "mdi:database-outline",
                "category": "config"
            },
            {
                "type": "number",
                "key": "detection_interval_sec",
                "name": "Detection Interval",
                "default": self.DEFAULT_DETECTION_INTERVAL_SEC,
                "min": 30,
                "max": 300,
                "step": 30,
                "unit": "s",
                "icon": "mdi:timer-outline",
                "category": "config"
            },
            
            # Feature flags
            {
                "type": "switch",
                "key": "enable_statistical_detection",
                "name": "Enable Statistical Detection",
                "default": self.DEFAULT_ENABLE_STATISTICAL_DETECTION,
                "icon": "mdi:chart-bell-curve",
                "category": "config"
            },
            {
                "type": "switch", 
                "key": "enable_strategic_override",
                "name": "Enable Strategic Override",
                "default": self.DEFAULT_ENABLE_STRATEGIC_OVERRIDE,
                "icon": "mdi:strategy",
                "category": "config"
            },
            {
                "type": "switch",
                "key": "enable_extreme_peak_boost",
                "name": "Enable Extreme Peak Boost",
                "default": self.DEFAULT_ENABLE_EXTREME_PEAK_BOOST,
                "icon": "mdi:rocket-launch-outline",
                "category": "config"
            },
            {
                "type": "switch",
                "key": "enable_real_time_alerts",
                "name": "Enable Real-time Alerts",
                "default": self.DEFAULT_ENABLE_REAL_TIME_ALERTS,
                "icon": "mdi:bell-alert-outline",
                "category": "config"
            }
        ]
    
    def validate_config(self, config: PeakDetectionConfig) -> List[str]:
        """Validate peak detection configuration and return list of issues."""
        issues = []
        
        if config.statistical_threshold < 1.0:
            issues.append("Statistical threshold too low (< 1.0)")
        elif config.statistical_threshold > 5.0:
            issues.append("Statistical threshold too high (> 5.0)")
        
        if config.strategic_override_multiplier < 1.05:
            issues.append("Strategic override multiplier too low (< 1.05)")
        elif config.strategic_override_multiplier > 2.0:
            issues.append("Strategic override multiplier too high (> 2.0)")
        
        if config.extreme_peak_multiplier < config.strategic_override_multiplier:
            issues.append("Extreme peak multiplier should be >= strategic override multiplier")
        
        if config.rolling_window_hours < 6:
            issues.append("Rolling window too short (< 6 hours)")
        elif config.rolling_window_hours > 168:
            issues.append("Rolling window too long (> 168 hours)")
        
        if config.min_historical_points < 6:
            issues.append("Minimum historical points too low (< 6)")
        
        if config.detection_interval_sec < 30:
            issues.append("Detection interval too frequent (< 30 seconds)")
        elif config.detection_interval_sec > 300:
            issues.append("Detection interval too slow (> 300 seconds)")
        
        return issues