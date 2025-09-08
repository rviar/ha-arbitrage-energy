# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Home Assistant custom integration for **Energy Arbitrage** - automated energy trading using solar panels, battery storage, and dynamic electricity pricing. The system implements predictive algorithms to optimize battery charging/discharging for maximum profit while ensuring energy security.

### Home Assistant Integration Testing

- Install via HACS or copy to `custom_components/energy_arbitrage/`
- Restart Home Assistant
- Add integration via UI: Settings → Devices & Services → Add Integration → Energy Arbitrage
- Monitor logs: `tail -f home-assistant.log | grep energy_arbitrage`

### Testing Commands

```bash
# Test timezone refactoring (CRITICAL for arbitrage accuracy)
python3 test_timezone_refactor.py

# Test individual modules if available
python3 test_price_extremes.py
python3 test_coordinator_fixes.py
```

## Architecture Overview

### Core Structure

```
custom_components/energy_arbitrage/
├── __init__.py              # Integration setup & coordinator initialization
├── coordinator.py           # DataUpdateCoordinator - main orchestration
├── config_flow.py          # UI configuration wizard
├── sensor.py               # All sensor entities (40+ sensors)
├── switch.py               # Control switches (enabled, emergency mode, etc.)
├── number.py              # Configurable parameters
├── const.py               # Constants and defaults
└── arbitrage/             # Core arbitrage logic modules
    ├── predictor.py       # Energy balance prediction
    ├── time_analyzer.py   # Time window analysis
    ├── strategic_planner.py # Long-term planning
    ├── optimizer.py       # Decision optimizer
    ├── executor.py        # Action execution
    ├── utils.py          # Utility functions
    └── sensor_data_helper.py # Data collection helpers
```

### Data Architecture Principle

**CRITICAL:** The system follows a strict **sensor-centric architecture** where all data flows through Home Assistant sensors. Algorithms must ONLY consume data from sensors, never directly from entity_id sources or configuration.

**TIMEZONE CRITICAL:** All datetime operations use Home Assistant's configured timezone, never UTC or system timezone. MQTT price data (in UTC) is automatically converted to HA timezone for accurate arbitrage timing.

#### Data Flow Hierarchy:

1. **Input Data Sensors** - External data sources (prices, PV, battery levels)
2. **Configuration Parameter Sensors** - User settings exposed as sensors
3. **Algorithm Processing** - Reads ONLY from sensors, never config files
4. **Output/Decision Sensors** - Results published as sensors

### Three-Tier Predictive System

#### 1. EnergyBalancePredictor (`predictor.py`)

- Analyzes Solcast PV forecasts for today/tomorrow
- Estimates home consumption patterns
- Determines energy surplus/deficit scenarios
- Recommends strategies: `charge_aggressive`, `charge_moderate`, `sell_aggressive`, `sell_partial`, `hold`

#### 2. TimeWindowAnalyzer (`time_analyzer.py`)

- Processes MQTT price data to find optimal time windows
- Identifies sequential periods of low/high prices
- Calculates time pressure: `high`, `medium`, `low`
- Plans operations considering battery power constraints

#### 3. StrategicPlanner (`strategic_planner.py`)

- Creates 24-48 hour operational plans
- Manages complex scenarios: `energy_critical_deficit`, `surplus_both_days`, `transition_periods`
- Optimizes operation sequences
- Generates backup plans for risky scenarios

#### 4. ArbitrageOptimizer (`optimizer.py`)

- Implements 5-tier decision hierarchy
- Executes real-time decision making
- Manages inverter mode transitions
- Handles safety checks and constraints

## Key Components

### DataUpdateCoordinator (`coordinator.py`)

- Central orchestration point
- Manages all sensor updates
- Coordinates between predictive modules
- Handles MQTT price data integration
- Updates every 60 seconds (configurable)

### Sensor System (`sensor.py`)

**40+ sensors organized by category:**

- **Input Data:** Current prices, battery levels, power readings
- **Configuration:** All user settings exposed as sensors
- **Predictive:** Energy forecasts, price windows, strategic plans
- **Output:** Target power, profit forecasts, ROI calculations
- **Status:** System status, debug information

### Safety and Constraints

- **Battery protection:** Minimum reserve levels, cycle limiting
- **Power limits:** Maximum charge/discharge rates
- **Time constraints:** Cooldown periods between actions
- **Degradation tracking:** Battery wear calculations
- **Emergency modes:** Manual overrides and safety shutoffs

## Configuration System

### Multi-Step UI Configuration:

1. **Solar & Energy Sensors** - Entity ID selection
2. **Inverter Controls** - Work mode and charging switches
3. **MQTT Price Topics** - Dynamic tariff sources
4. **System Parameters** - Battery specs, limits, algorithms

### Default Entity Mappings:

- **Solar:** `sensor.inverter_pv_power`, Solcast forecasts
- **Battery:** `sensor.inverter_battery`, `sensor.inverter_battery_power`
- **Energy:** `sensor.inverter_load_power`, `sensor.inverter_grid_power`
- **Control:** `select.inverter_work_mode`, `switch.inverter_battery_grid_charging`
- **MQTT:** `energy/forecast/buy`, `energy/forecast/sell`

## Inverter Control Logic

### Arbitrage Modes:

- **Charge Arbitrage:** `Grid Charging=True`, `Export Surplus=False`, `ToU=Disabled`
- **Sell Arbitrage:** `Work Mode=Export First`, `Grid Charging=False`, `ToU=Enabled`
- **Hold Mode:** `Work Mode=Zero Export`, `ToU=Enabled`, `Export Surplus=True`

### Decision Priority Hierarchy:

1. **Strategic Decisions** (confidence ≥ 0.8) - Long-term energy planning
2. **Time Critical** (high time pressure) - Expiring price windows
3. **Predictive Planned** - Scheduled operations
4. **Predictive Standard** - Standard energy balance
5. **Traditional Arbitrage** - Opportunistic trading
6. **Strategic Hold** (default) - Intelligent waiting

## Development Patterns

### Adding New Sensors:

1. Define constants in `const.py`
2. Add sensor class in `sensor.py`
3. Register in `coordinator.py`
4. Update config flow if needed

### Algorithm Development:

- **MUST** read data only through `get_sensor_value()` method
- **NEVER** access config directly or external entity_id
- All algorithms work with standardized sensor data
- Results published through coordinator updates

### Timezone Requirements (CRITICAL):

- **ALWAYS** use `get_current_ha_time(hass)` instead of `datetime.now()`
- **NEVER** use `datetime.now(timezone.utc)` - use HA timezone
- **MQTT data** is automatically converted from UTC to HA timezone
- **Import** timezone utilities: `from .arbitrage.utils import get_current_ha_time, get_ha_timezone, parse_datetime`

### Testing Approach:

- Individual module testing with Python scripts
- Integration testing in Home Assistant development environment
- Real-world testing with actual inverter hardware
- Price simulation with historical MQTT data

## Key Constants and Defaults

```python
DEFAULT_MAX_PV_POWER = 10600        # 10.6 kW
DEFAULT_BATTERY_CAPACITY = 15000    # 15 kWh
DEFAULT_MAX_BATTERY_POWER = 6500    # 6.5 kW
DEFAULT_MIN_ARBITRAGE_MARGIN = 15   # 15%
DEFAULT_MAX_DAILY_CYCLES = 2.0      # Battery protection
DEFAULT_MIN_ARBITRAGE_DEPTH = 40    # 40% minimum SOC
DEFAULT_CURRENCY = "PLN"
```

## Debugging and Troubleshooting

### Common Issues:

- **MQTT connectivity:** Check broker availability and topic formats
- **Solcast integration:** Verify API limits and sensor availability
- **Inverter control:** Ensure proper entity_id access permissions
- **Price data format:** MQTT messages must be JSON arrays

### Logging:

- Main logs: `_LOGGER.info/debug/warning` in coordinator
- Algorithm traces in each arbitrage module
- Sensor state changes logged automatically by HA

### Configuration Validation:

- Entity ID existence checked during setup
- Numeric parameter bounds enforced
- MQTT topic format validation
- Battery specification consistency checks

## Integration Dependencies

- **Home Assistant:** 2024.1.0+
- **MQTT Integration:** For price data
- **Solcast Integration:** For PV forecasts (recommended)
- **Solarman Integration:** For inverter control (recommended)

## Language and Documentation

The codebase contains both English code/comments and Russian documentation. When making changes:

- Keep code, variable names, and technical comments in English
- Preserve Russian user-facing text and documentation
- All entity names and sensor attributes should remain in English for HA compatibility
