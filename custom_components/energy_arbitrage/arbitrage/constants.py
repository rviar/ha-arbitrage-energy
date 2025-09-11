"""
Constants for energy arbitrage calculations and decision making.
Centralizes magic numbers for better maintainability.
"""

# Time Constants (in seconds)
SECONDS_PER_HOUR = 3600
SECONDS_PER_30_MINUTES = 1800
SECONDS_PER_15_MINUTES = 900

# Confidence Thresholds
CONFIDENCE_HIGH = 0.8
CONFIDENCE_MEDIUM = 0.7
CONFIDENCE_LOW = 0.5
CONFIDENCE_STRATEGIC_DECISION = 0.7  # Minimum confidence for strategic decisions
CONFIDENCE_OPPORTUNISTIC_MULTIPLIER = 0.8  # Multiplier for opportunistic operations

# Battery Management
MAX_BATTERY_LEVEL = 95.0  # Maximum safe battery charge level
BATTERY_CHARGE_AGGRESSIVE_MARGIN = 0.7  # Reduced margin for aggressive charging
BATTERY_POWER_CONSERVATIVE_MULTIPLIER = 0.8  # Conservative power usage multiplier
BATTERY_DISCHARGE_CONSERVATIVE_MULTIPLIER = 0.6  # Conservative discharge multiplier
TARGET_ENERGY_ACCEPTABLE_THRESHOLD = 0.8  # 80% of target energy is acceptable

# ROI and Pricing
HIGH_ROI_MULTIPLIER = 1.5  # Minimum ROI multiplier for traditional arbitrage fallback
PRICE_ANALYSIS_THRESHOLD_MULTIPLIER = 0.8  # Threshold for price extremes detection
MIN_SPREAD_PERCENT = 5.0  # Minimum spread percent between sell and buy to consider trading

# Time Pressure and Urgency
HIGH_PRESSURE_TIME_LIMIT = 3600  # Less than 1 hour = high time pressure (seconds)
STRATEGIC_PLAN_UPDATE_INTERVAL = 1800  # Update strategic plans every 30 minutes

# Energy Thresholds
MIN_ENERGY_FOR_SELL = 1000  # Minimum Wh available to consider selling
DEFAULT_DAILY_CONSUMPTION_WH = 18000  # Default daily consumption estimate
MIN_TRADE_ENERGY_WH = 500  # Minimum energy per trade to avoid micro-cycles
SURPLUS_POWER_IGNORE_W = 100  # Ignore tiny PV surplus below this when deciding grid buys
PV_SURPLUS_BLOCK_MARGIN_PERCENT = 3.0  # Allow small margin when comparing forecast PV charge to target

# Battery Level Adjustments
STRATEGIC_CHARGE_LEVEL_ADJUSTMENT = 20  # Battery level increase for strategic charging
STRATEGIC_DISCHARGE_LEVEL_ADJUSTMENT = 15  # Battery level decrease for strategic discharging
AGGRESSIVE_CHARGE_ADJUSTMENT = 15  # Aggressive charging level adjustment
MODERATE_CHARGE_ADJUSTMENT = 10  # Moderate charging level adjustment
CONSERVATIVE_DISCHARGE_ADJUSTMENT = 10  # Conservative discharge adjustment
AGGRESSIVE_DISCHARGE_ADJUSTMENT = 20  # Aggressive discharge adjustment

# Confidence Adjustment Factors
CONFIDENCE_PEAK_DATA_AVAILABLE = 0.85  # Confidence when peak data is available
CONFIDENCE_NO_PEAK_DATA = 0.8  # Confidence when no peak data available

# Planning Horizons
DEFAULT_ANALYSIS_HORIZON_HOURS = 24  # Default time window for analysis
STRATEGIC_PLANNING_HORIZON_HOURS = 48  # Strategic planning horizon
BATTERY_DISCHARGE_HOURS = 2  # Default hours for battery discharge calculation

# System Defaults (fallback values when sensors unavailable)
FALLBACK_BATTERY_CAPACITY_WH = 15000  # Fallback battery capacity
FALLBACK_BATTERY_RESERVE_PERCENT = 50  # Fallback minimum battery reserve

# Time Tolerance
TIME_WINDOW_TOLERANCE_MINUTES = 30  # Tolerance for time window matching
TRADE_COOLDOWN_MINUTES = 45  # Cooldown between consecutive trades of same type

# Price Analysis Windows
PRICE_ANALYSIS_24H_WINDOW = 24  # Hours for 24-hour price extremes analysis
TOP_RESULTS_LIMIT = 3  # Maximum number of top results to consider

# Energy Calculations
ENERGY_CALCULATION_1KWH = 1000  # 1kWh in Wh for profit calculations
PRICE_COMPARISON_TOLERANCE = 0.001  # Tolerance for price equality comparison

# Time Approximations (hours)
FUTURE_BUY_TIME_OFFSET = 12  # Hours offset for future buy time approximation
FUTURE_SELL_TIME_OFFSET = 18  # Hours offset for future sell time approximation
NEAR_TERM_REBUY_LOOKAHEAD_HOURS = 6  # Lookahead window for sell-now, rebuy-soon analysis

# Battery Specifications (defaults)
DEFAULT_BATTERY_COST = 7500  # Default battery cost in currency units
DEFAULT_BATTERY_CYCLES = 6000  # Default battery cycle life
DEFAULT_DEGRADATION_FACTOR = 1.0  # Default battery degradation factor

# Price Window Analysis
PRICE_QUARTILE_DIVISOR = 4  # Divisor for quartile calculations
PRICE_TOLERANCE_HIGH_MULTIPLIER = 1.1  # 110% for upper price tolerance
PRICE_TOLERANCE_LOW_MULTIPLIER = 0.9  # 90% for lower price tolerance

# Urgency Thresholds (hours)
URGENCY_HIGH_THRESHOLD_HOURS = 1  # High urgency if starting within 1 hour
URGENCY_MEDIUM_THRESHOLD_HOURS = 4  # Medium urgency if starting within 4 hours

# Peak Time Analysis
PEAK_TIMES_TOP_N = 3  # Number of peak times to identify per window

# Fallback Values
FALLBACK_BATTERY_LEVEL_PERCENT = 50.0  # Fallback battery level when sensors fail
FALLBACK_CONFIDENCE_LEVEL = 0.3  # Fallback confidence for error conditions