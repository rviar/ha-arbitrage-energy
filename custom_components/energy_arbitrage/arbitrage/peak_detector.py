"""
Exceptional Peak Detection for Energy Arbitrage
Detects statistical outliers and market anomalies for immediate action override.
"""

import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .constants import (
    PEAK_DETECTION_Z_SCORE_THRESHOLD, PEAK_DETECTION_EXTREME_MULTIPLIER,
    PEAK_DETECTION_STRATEGIC_OVERRIDE_MULTIPLIER, PEAK_DETECTION_HISTORICAL_LOOKBACK_HOURS,
    PEAK_DETECTION_MIN_DURATION_MINUTES, PEAK_DETECTION_FALSE_POSITIVE_COOLDOWN_MINUTES
)
from .utils import get_current_ha_time, parse_datetime
from .exceptions import safe_execute

_LOGGER = logging.getLogger(__name__)

class PeakType(Enum):
    """Types of detected peaks."""
    STATISTICAL_OUTLIER = "statistical_outlier"
    EXTREME_PEAK = "extreme_peak"
    STRATEGIC_OVERRIDE = "strategic_override"
    NORMAL = "normal"

@dataclass
class PeakAnalysis:
    """Results of peak detection analysis."""
    peak_type: PeakType
    current_price: float
    z_score: float
    percentile_95: float
    baseline_mean: float
    baseline_std: float
    deviation_ratio: float
    confidence: float
    should_override: bool
    urgency: str  # low, medium, high, critical
    recommended_action: str
    analysis_timestamp: datetime
    
    @property
    def is_exceptional(self) -> bool:
        """True if this is an exceptional peak requiring immediate action."""
        return self.peak_type in [PeakType.STATISTICAL_OUTLIER, PeakType.EXTREME_PEAK, PeakType.STRATEGIC_OVERRIDE]
    
    @property
    def profit_multiplier(self) -> float:
        """Estimated profit multiplier compared to normal arbitrage."""
        return min(self.deviation_ratio, 3.0)  # Cap at 3x for safety

class ExceptionalPeakDetector:
    """
    Detects exceptional price peaks for immediate arbitrage override.
    
    Integrates with Home Assistant energy arbitrage system to identify
    statistical outliers and market anomalies that warrant overriding
    strategic plans for immediate profit capture.
    """
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
        self._price_history: List[Dict] = []
        self._peak_history: List[PeakAnalysis] = []
        self._last_override_time: Optional[datetime] = None
        self._configuration_cache = {}
        self._statistics_cache = {}
        
        # Performance optimization
        self._cache_timeout = 300  # 5 minutes
        self._max_history_size = 1000
        
    def _get_configuration(self, key: str, default: Any) -> Any:
        """Get configuration from coordinator with caching."""
        if not self.coordinator or not hasattr(self.coordinator, 'data'):
            return default
            
        cache_key = f"config_{key}"
        current_time = get_current_ha_time()
        
        # Check cache
        if cache_key in self._configuration_cache:
            cached_value, cached_time = self._configuration_cache[cache_key]
            if (current_time - cached_time).total_seconds() < self._cache_timeout:
                return cached_value
        
        # Get from coordinator
        coordinator_data = self.coordinator.data or {}
        options = coordinator_data.get('options', {})
        config = coordinator_data.get('config', {})
        
        value = options.get(key, config.get(key, default))
        self._configuration_cache[cache_key] = (value, current_time)
        
        return value
    
    @safe_execute(default_return=False)
    def is_enabled(self) -> bool:
        """Check if peak detection is enabled."""
        return self._get_configuration('peak_detection_enabled', True)
    
    @safe_execute(default_return=[])
    def _get_recent_price_history(self, hours: int = None) -> List[Dict]:
        """Get recent price history for analysis."""
        if hours is None:
            hours = self._get_configuration('peak_detection_lookback_hours', PEAK_DETECTION_HISTORICAL_LOOKBACK_HOURS)
        
        if not self.coordinator or not self.coordinator.data:
            return []
        
        # Get price data from coordinator
        price_data = self.coordinator.data.get('price_data', {})
        sell_prices = price_data.get('sell_prices', [])
        
        if not sell_prices:
            return []
        
        # Filter to recent hours
        current_time = get_current_ha_time()
        cutoff_time = current_time - timedelta(hours=hours)
        
        recent_prices = []
        for price_entry in sell_prices:
            timestamp_str = price_entry.get('start', '')
            timestamp = parse_datetime(timestamp_str)
            
            if timestamp and timestamp >= cutoff_time:
                recent_prices.append({
                    'timestamp': timestamp,
                    'price': price_entry.get('value', 0.0),
                    'raw_entry': price_entry
                })
        
        # Sort by timestamp
        recent_prices.sort(key=lambda x: x['timestamp'])
        
        # Limit size for performance
        if len(recent_prices) > self._max_history_size:
            recent_prices = recent_prices[-self._max_history_size:]
        
        return recent_prices
    
    @safe_execute(default_return=(0.0, 0.0, 0.0))
    def _calculate_baseline_statistics(self, price_history: List[Dict]) -> Tuple[float, float, float]:
        """Calculate baseline statistics from price history."""
        if len(price_history) < 3:
            return 0.0, 0.0, 0.0
        
        prices = [entry['price'] for entry in price_history]
        
        try:
            mean_price = statistics.mean(prices)
            std_price = statistics.stdev(prices) if len(prices) > 1 else 0.0
            percentile_95 = sorted(prices)[int(0.95 * len(prices))] if len(prices) >= 5 else max(prices)
            
            return mean_price, std_price, percentile_95
        except (ValueError, TypeError):
            return 0.0, 0.0, 0.0
    
    @safe_execute(default_return=PeakAnalysis(
        PeakType.NORMAL, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, False, "low", "hold", datetime.now()
    ))
    def analyze_current_price(self, current_price: float, strategic_plan_price: float = None) -> PeakAnalysis:
        """
        Analyze current price for exceptional peaks.
        
        Args:
            current_price: Current sell price in PLN/kWh
            strategic_plan_price: Expected price from strategic plan
            
        Returns:
            PeakAnalysis with detection results and recommendations
        """
        analysis_time = get_current_ha_time()
        
        # Get recent price history
        price_history = self._get_recent_price_history()
        
        if len(price_history) < 3:
            _LOGGER.debug("Insufficient price history for peak analysis")
            return PeakAnalysis(
                peak_type=PeakType.NORMAL,
                current_price=current_price,
                z_score=0.0,
                percentile_95=current_price,
                baseline_mean=current_price,
                baseline_std=0.0,
                deviation_ratio=1.0,
                confidence=0.0,
                should_override=False,
                urgency="low",
                recommended_action="hold",
                analysis_timestamp=analysis_time
            )
        
        # Calculate baseline statistics
        baseline_mean, baseline_std, percentile_95 = self._calculate_baseline_statistics(price_history)
        
        # Calculate z-score
        z_score = (current_price - baseline_mean) / baseline_std if baseline_std > 0 else 0.0
        deviation_ratio = current_price / baseline_mean if baseline_mean > 0 else 1.0
        
        # Get configuration thresholds
        z_threshold = self._get_configuration('peak_detection_z_threshold', PEAK_DETECTION_Z_SCORE_THRESHOLD)
        extreme_multiplier = self._get_configuration('peak_detection_extreme_multiplier', PEAK_DETECTION_EXTREME_MULTIPLIER)
        strategic_multiplier = self._get_configuration('peak_detection_strategic_multiplier', PEAK_DETECTION_STRATEGIC_OVERRIDE_MULTIPLIER)
        
        # Determine peak type and characteristics
        peak_type = PeakType.NORMAL
        should_override = False
        urgency = "low"
        recommended_action = "hold"
        confidence = 0.0
        
        # Check for statistical outlier
        if abs(z_score) >= z_threshold:
            peak_type = PeakType.STATISTICAL_OUTLIER
            confidence = min(abs(z_score) / 3.0, 1.0)  # Normalize confidence
            should_override = True
            urgency = "high" if abs(z_score) >= 2.0 else "medium"
            recommended_action = "sell_immediate" if current_price > baseline_mean else "hold"
            
            _LOGGER.info(f"🚨 Statistical outlier detected: {current_price:.4f} PLN/kWh (z={z_score:.2f})")
        
        # Check for extreme peak (above 95th percentile)
        elif current_price >= percentile_95 * extreme_multiplier:
            peak_type = PeakType.EXTREME_PEAK
            confidence = min((current_price / percentile_95 - 1.0) * 2.0, 1.0)
            should_override = True
            urgency = "critical" if current_price >= percentile_95 * 1.5 else "high"
            recommended_action = "sell_maximum_power"
            
            _LOGGER.info(f"💎 Extreme peak detected: {current_price:.4f} PLN/kWh (>{percentile_95 * extreme_multiplier:.4f})")
        
        # Check for strategic override
        elif strategic_plan_price and current_price >= strategic_plan_price * strategic_multiplier:
            peak_type = PeakType.STRATEGIC_OVERRIDE
            confidence = min((current_price / strategic_plan_price - 1.0) * 3.0, 1.0)
            should_override = True
            urgency = "critical" if current_price >= strategic_plan_price * 1.2 else "high"
            recommended_action = "sell_override_strategic"
            
            _LOGGER.info(f"⚡ Strategic override triggered: {current_price:.4f} vs planned {strategic_plan_price:.4f} PLN/kWh")
        
        # Create analysis result
        analysis = PeakAnalysis(
            peak_type=peak_type,
            current_price=current_price,
            z_score=z_score,
            percentile_95=percentile_95,
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            deviation_ratio=deviation_ratio,
            confidence=confidence,
            should_override=should_override,
            urgency=urgency,
            recommended_action=recommended_action,
            analysis_timestamp=analysis_time
        )
        
        # Store in history
        self._peak_history.append(analysis)
        if len(self._peak_history) > 100:  # Keep last 100 analyses
            self._peak_history = self._peak_history[-100:]
        
        return analysis
    
    @safe_execute(default_return=False)
    def should_override_strategic_plan(self, current_price: float, strategic_plan) -> bool:
        """
        Determine if current conditions warrant overriding the strategic plan.
        
        Args:
            current_price: Current market price
            strategic_plan: Active strategic plan object
            
        Returns:
            True if strategic plan should be overridden
        """
        if not self.is_enabled():
            return False
        
        # Check cooldown period to prevent rapid-fire overrides
        if self._last_override_time:
            cooldown_minutes = self._get_configuration(
                'peak_detection_cooldown_minutes', 
                PEAK_DETECTION_FALSE_POSITIVE_COOLDOWN_MINUTES
            )
            time_since_override = (get_current_ha_time() - self._last_override_time).total_seconds() / 60
            if time_since_override < cooldown_minutes:
                _LOGGER.debug(f"Peak detection in cooldown: {time_since_override:.1f}min < {cooldown_minutes}min")
                return False
        
        # Get strategic plan price
        strategic_price = None
        if strategic_plan and hasattr(strategic_plan, 'next_operation') and strategic_plan.next_operation:
            strategic_price = strategic_plan.next_operation.expected_price
        
        # Analyze current price
        analysis = self.analyze_current_price(current_price, strategic_price)
        
        if analysis.should_override:
            self._last_override_time = get_current_ha_time()
            _LOGGER.warning(f"🚨 Peak override activated: {analysis.peak_type.value} - {analysis.recommended_action}")
            return True
        
        return False
    
    def get_peak_statistics(self) -> Dict[str, Any]:
        """Get statistics about peak detection performance."""
        if not self._peak_history:
            return {
                'total_peaks_detected': 0,
                'overrides_triggered': 0,
                'average_confidence': 0.0,
                'peak_types_count': {},
                'last_peak_time': None
            }
        
        # Calculate statistics
        total_peaks = len([p for p in self._peak_history if p.is_exceptional])
        overrides = len([p for p in self._peak_history if p.should_override])
        avg_confidence = statistics.mean([p.confidence for p in self._peak_history if p.is_exceptional]) if total_peaks > 0 else 0.0
        
        # Count peak types
        peak_types = {}
        for analysis in self._peak_history:
            if analysis.is_exceptional:
                peak_type = analysis.peak_type.value
                peak_types[peak_type] = peak_types.get(peak_type, 0) + 1
        
        # Get last exceptional peak
        exceptional_peaks = [p for p in self._peak_history if p.is_exceptional]
        last_peak_time = exceptional_peaks[-1].analysis_timestamp.isoformat() if exceptional_peaks else None
        
        return {
            'total_peaks_detected': total_peaks,
            'overrides_triggered': overrides,
            'average_confidence': round(avg_confidence, 2),
            'peak_types_count': peak_types,
            'last_peak_time': last_peak_time,
            'analysis_history_size': len(self._peak_history),
            'price_history_size': len(self._get_recent_price_history())
        }
    
    def reset_statistics(self):
        """Reset peak detection statistics and history."""
        self._peak_history.clear()
        self._last_override_time = None
        _LOGGER.info("Peak detection statistics reset")