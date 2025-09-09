# Energy Arbitrage Peak Detection Enhancement Workflow

## Project Overview

**Problem**: The system missed a critical 1.85 PLN/kWh price peak (19:00-20:00 CEST) while focusing on a strategic plan targeting 1.72 PLN/kWh for tomorrow. This represents a ~357% profit opportunity loss and highlights critical gaps in real-time peak detection.

**Solution**: Implement a comprehensive peak detection system that can override strategic plans when exceptional market opportunities arise.

## 📊 Root Cause Analysis

### Issue 1: Peak Detection Algorithm Bug
- **Problem**: Time analyzer's quartile-based filtering failed to detect 1.85 PLN/kWh peak
- **Root Cause**: Algorithm uses PRICE_QUARTILE_DIVISOR=4 with 90% multiplier, may exclude statistical outliers
- **Impact**: Missed best opportunity in 48h price data

### Issue 2: Strategic Plan Override Limitation  
- **Problem**: No mechanism to override strategic plans for exceptional opportunities
- **Root Cause**: 5-tier priority system strictly follows strategic plans (90% confidence)
- **Impact**: System waits 22h for inferior opportunity (1.72 vs 1.85)

### Issue 3: Real-time Monitoring Gap
- **Problem**: Insufficient current-hour price monitoring
- **Root Cause**: System optimizes for windows, not immediate opportunities  
- **Impact**: Missed live peak while it was happening

## 🎯 Implementation Strategy

### Phase 1: Core Peak Detection Enhancement (Weeks 1-2)

**Objective**: Add statistical peak detection with real-time processing

#### 1.1 ExceptionalPeakDetector Class
```python
# File: /arbitrage/peak_detector.py
class ExceptionalPeakDetector:
    - Statistical outlier detection (z-score, IQR)
    - Rolling window analysis (24h baseline)
    - Multi-threshold configuration
    - Real-time processing optimization
```

**Key Features**:
- Z-score analysis for outlier detection (>1.5σ configurable)
- Historical percentile comparison (95th percentile baseline)
- Strategic override threshold (110% of planned price)
- Performance: <5 second detection latency

#### 1.2 Enhanced TimeWindowAnalyzer
```python
# File: /arbitrage/time_analyzer.py (modifications)
- Add peak_detector integration
- Implement dynamic threshold adjustment
- Single-hour window preservation
- Real-time opportunity flagging
```

**Improvements**:
- Preserve single-hour high-value windows
- Add absolute peak detection (top-N approach)
- Dynamic threshold based on market volatility
- Enhanced logging for debugging

### Phase 2: Decision System Integration (Weeks 3-4)

**Objective**: Integrate peak detection into decision hierarchy

#### 2.1 Priority System Enhancement
```
NEW PRIORITY ORDER:
0. EXCEPTIONAL_PEAK (NEW - highest priority)
1. STRATEGIC_PLAN (existing)  
2. TIME_CRITICAL (existing)
3. PLANNED_PREDICTIVE (existing)
4. STANDARD_PREDICTIVE (existing)
5. TRADITIONAL_ARBITRAGE (existing)
```

#### 2.2 PeakOverrideDecisionHandler
```python
# File: /arbitrage/decision_handlers.py (new handler)
class PeakOverrideDecisionHandler(DecisionHandler):
    - Exceptional peak detection
    - Strategic plan override logic
    - Risk management integration
    - Immediate action triggers
```

**Decision Logic**:
- If current_price > strategic_price × 1.10 → Override
- If z_score > 1.5σ threshold → Immediate action
- If price > 95th_percentile × 1.20 → Maximum power discharge
- Include safety checks and battery level validation

### Phase 3: Configuration & Monitoring (Weeks 5-6)

**Objective**: Add user configuration and comprehensive monitoring

#### 3.1 Home Assistant Entities
```yaml
# Configuration entities to add:
- Peak detection enable/disable switch
- Z-score threshold (number: 1.0-3.0)  
- Strategic override multiplier (number: 1.05-1.30)
- Historical lookback period (number: 12-48h)
- Maximum peak power percentage (number: 50-100%)
```

#### 3.2 Monitoring & Status
```yaml
# Status sensors to add:
- Peak detection status (active/inactive)
- Last peak detected (timestamp + price)
- Strategic overrides today (count)
- Exceptional peak profit (daily total)
- False positive rate (monitoring)
```

## 🏗️ Technical Implementation Details

### Architecture Integration
```
┌─────────────────────────────────────────┐
│ Layer 5: EXCEPTIONAL PEAK DETECTION    │ ← NEW
│ - ExceptionalPeakDetector               │
│ - PeakOverrideDecisionHandler           │
│ - Real-time monitoring                  │
└─────────────────────────────────────────┘
           ↓ (Override trigger)
┌─────────────────────────────────────────┐
│ Layer 4: STRATEGIC PLANNING (existing) │
│ - Strategic plans (90% confidence)      │
│ - 48h optimization                      │
└─────────────────────────────────────────┘
           ↓ (Normal flow continues)
┌─────────────────────────────────────────┐
│ Layers 1-3: Existing Architecture      │
│ - Time analysis, Energy prediction     │
│ - Price windows, PV forecasts          │
└─────────────────────────────────────────┘
```

### Data Flow
1. **MQTT Price Data** → ExceptionalPeakDetector
2. **Peak Analysis** → Statistical evaluation + threshold comparison
3. **Override Decision** → PeakOverrideDecisionHandler
4. **Action Execution** → Direct to ArbitrageExecutor (bypass strategic plan)
5. **Monitoring** → Update HA sensors with peak statistics

### Algorithm Specifications

#### Statistical Peak Detection
```python
def detect_statistical_peak(current_price, price_history_24h):
    baseline_mean = np.mean(price_history_24h)
    baseline_std = np.std(price_history_24h)
    z_score = (current_price - baseline_mean) / baseline_std
    
    percentile_95 = np.percentile(price_history_24h, 95)
    
    return {
        'is_statistical_outlier': z_score > Z_SCORE_THRESHOLD,
        'is_extreme_peak': current_price > percentile_95 * EXTREME_MULTIPLIER,
        'z_score': z_score,
        'deviation_ratio': current_price / baseline_mean
    }
```

#### Strategic Override Logic
```python
def should_override_strategic_plan(current_price, strategic_plan):
    if not strategic_plan or not strategic_plan.next_operation:
        return False
        
    planned_price = strategic_plan.next_operation.expected_price
    price_multiplier = current_price / planned_price
    
    return price_multiplier >= STRATEGIC_OVERRIDE_MULTIPLIER
```

## 🧪 Testing & Validation

### Unit Tests
```python
# Tests to implement:
- test_1_85_peak_detection()  # Reproduce the missed peak scenario
- test_statistical_outlier_detection()
- test_strategic_override_logic() 
- test_false_positive_prevention()
- test_performance_benchmarks()
```

### Integration Tests
```python
# Full system tests:
- test_peak_to_action_flow()  # End-to-end peak detection → execution
- test_normal_operation_preservation()  # Ensure existing functionality
- test_configuration_integration()  # HA entity configuration
- test_monitoring_accuracy()  # Sensor data validation
```

### Performance Benchmarks
- Peak detection latency: < 5 seconds
- Memory usage increase: < 50MB
- CPU impact: < 2% additional load
- False positive rate: < 5%

## 📈 Success Metrics

### Functional Metrics
- **Peak Detection Accuracy**: >95% for 1.5σ outliers
- **Strategic Override Accuracy**: >99% for threshold breaches
- **System Responsiveness**: <5s from price update to action
- **Backward Compatibility**: 100% existing functionality preserved

### Business Metrics  
- **Missed Opportunity Reduction**: <1% of exceptional peaks missed
- **Profit Enhancement**: 15-25% increase in total arbitrage profit
- **Response Time**: <30 minutes for critical peaks
- **False Action Rate**: <2% inappropriate overrides

## 🔧 Configuration Parameters

### Peak Detection Settings
```yaml
peak_detection_enabled: true           # Master enable/disable
z_score_threshold: 1.5                # Statistical outlier sensitivity
strategic_override_multiplier: 1.10   # Override threshold (110%)
extreme_peak_multiplier: 1.20         # Extreme peak threshold (120% of 95th percentile)
historical_lookback_hours: 24         # Price history window
max_peak_power_percent: 90           # Maximum discharge power for peaks
min_peak_duration_minutes: 5         # Minimum peak duration
false_positive_cooldown_minutes: 30  # Prevent repeated false triggers
```

### Monitoring Configuration
```yaml
peak_statistics_retention_days: 30    # Historical peak data retention
override_logging_enabled: true        # Log all override decisions
performance_monitoring_enabled: true  # Track detection performance
alert_threshold_exceptional_peaks: 3   # Alert after 3+ peaks per day
```

## 🚀 Deployment Strategy

### Phase 1 Deployment
1. Deploy ExceptionalPeakDetector with feature flag disabled
2. Run parallel analysis (detect but don't act) for 1 week
3. Collect baseline performance and accuracy data
4. Validate against historical data including 1.85 PLN/kWh scenario

### Phase 2 Deployment  
1. Enable feature flag for beta testing
2. Start with conservative thresholds (z_score: 2.0, override: 1.20)
3. Monitor for 1 week with manual validation
4. Gradually optimize thresholds based on performance data

### Phase 3 Production
1. Full deployment with optimized thresholds  
2. Enable all monitoring and alerting
3. Document user configuration guidelines
4. Implement automated performance reporting

## 🎯 Expected Outcomes

### Immediate Benefits
- **Capture exceptional peaks**: System will detect and act on 1.85+ PLN/kWh opportunities
- **Reduce missed profits**: <1% of high-value peaks missed vs current ~100%  
- **Faster market response**: <5 minutes vs current 22+ hour strategic delays

### Long-term Benefits
- **Enhanced profitability**: 15-25% increase in total arbitrage profits
- **Market adaptability**: Better response to volatile energy markets
- **User confidence**: Transparent peak detection with detailed monitoring
- **System intelligence**: Self-optimizing thresholds based on market patterns

## 📋 Implementation Checklist

### Development Tasks
- [ ] Create ExceptionalPeakDetector class with statistical algorithms
- [ ] Enhance TimeWindowAnalyzer with peak preservation logic  
- [ ] Implement PeakOverrideDecisionHandler with override logic
- [ ] Add priority level 0 (EXCEPTIONAL_PEAK) to ArbitrageOptimizer
- [ ] Create configuration constants and validation
- [ ] Implement HA entity integration (switches, numbers, sensors)
- [ ] Add comprehensive logging and monitoring
- [ ] Create unit tests for all new components
- [ ] Implement integration tests for full workflow
- [ ] Performance optimization and memory management
- [ ] Documentation and user guides

### Validation Tasks  
- [ ] Test 1.85 PLN/kWh scenario reproduction
- [ ] Validate statistical accuracy on historical data
- [ ] Performance benchmarking (latency, memory, CPU)
- [ ] False positive rate measurement and optimization
- [ ] Backward compatibility verification
- [ ] Security review for new code paths
- [ ] User acceptance testing with real price feeds
- [ ] Production monitoring setup and alerting

This comprehensive workflow addresses the critical peak detection gap while maintaining the sophisticated strategic planning capabilities that make the energy arbitrage system unique. The implementation preserves backward compatibility while adding powerful real-time market response capabilities.