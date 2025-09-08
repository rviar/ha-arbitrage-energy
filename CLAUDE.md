# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This is a Home Assistant custom integration, so standard HA development practices apply:

- **No traditional build/test commands** - Integration is loaded directly by Home Assistant
- **Testing**: Run Home Assistant in development mode and load the integration
- **Linting**: Use `ruff` for Python code linting if available
- **Debugging**: Enable debug logging for `custom_components.energy_arbitrage` in HA configuration

## Architecture Overview

This is a **predictive energy arbitrage system** for Home Assistant that optimizes battery charging/discharging based on dynamic electricity pricing and solar forecasts.

### Core Architecture

The system uses a **3-layer predictive architecture**:

```
🔮 EnergyBalancePredictor → ⏰ TimeWindowAnalyzer → 🎯 StrategicPlanner → 🎲 ArbitrageOptimizer
```

1. **EnergyBalancePredictor** (`arbitrage/predictor.py`)
   - Analyzes 24-48h PV forecasts from Solcast
   - Predicts energy surplus/deficit scenarios
   - Recommends strategic energy management approaches

2. **TimeWindowAnalyzer** (`arbitrage/time_analyzer.py`) 
   - Identifies optimal price windows from MQTT data
   - Calculates time pressure and urgency levels
   - Plans precise timing for buy/sell operations

3. **StrategicPlanner** (`arbitrage/strategic_planner.py`)
   - Creates long-term operational plans (24-48h)
   - Manages complex scenarios (deficit→surplus transitions)
   - Generates backup plans for critical situations

4. **ArbitrageOptimizer** (`arbitrage/optimizer.py`)
   - Makes real-time decisions using 5-tier priority system
   - Executes strategic plans via inverter control
   - Handles safety checks and fallback logic

### Key Components

- **EnergyArbitrageCoordinator** (`coordinator.py`) - Main data coordinator, handles MQTT subscriptions
- **ArbitrageExecutor** (`arbitrage/executor.py`) - Inverter control interface  
- **SensorDataHelper** (`arbitrage/sensor_data_helper.py`) - Sensor data abstraction layer
- **Platform modules** (`sensor.py`, `switch.py`, `number.py`) - HA entity implementations

### Decision Priority Hierarchy

1. **Strategic** (confidence ≥ 0.8) - Critical energy planning decisions
2. **Time Critical** - Urgent price window opportunities  
3. **Planned Predictive** - Scheduled operations from strategic plan
4. **Standard Predictive** - Normal energy balance optimization
5. **Traditional Arbitrage** - Price-based opportunities (fallback)

### Data Flow

```
MQTT Price Data + Solcast PV Forecasts + HA Sensors
    ↓
EnergyArbitrageCoordinator (updates every 1 min)
    ↓
ArbitrageOptimizer.calculate_optimal_action()
    ↓
Strategic/Predictive Analysis → Decision → Inverter Control
    ↓
HA Entities (sensors, switches, numbers)
```

### Inverter Integration

Controls solar inverter through HA entities:
- `select.inverter_work_mode` - Operating mode (Export First, Zero Export, etc.)
- `switch.inverter_battery_grid_charging` - Grid charging control
- `select.inverter_time_of_use` - Time-of-use scheduling
- `switch.inverter_export_surplus` - Surplus export control

### Configuration Structure

Multi-step config flow in `config_flow.py`:
1. Solar & energy sensors selection
2. Inverter control entities  
3. MQTT topics for price data
4. System parameters (battery capacity, power limits, etc.)

### Safety Mechanisms

- **Battery protection**: Min reserve levels, cycle limits, depth restrictions
- **Manual override**: Temporary disable of automation
- **Emergency mode**: Preserve battery charge
- **Health checks**: System status monitoring via service calls

### Services

All services defined in `services.yaml` and implemented in `__init__.py`:
- `recalculate` - Force recalculation 
- `set_battery_reserve` - Adjust reserve levels
- `manual_override` - Temporary manual control
- `force_work_mode` - Direct inverter control
- `health_check` - System diagnostics

## File Structure Notes

- `/custom_components/energy_arbitrage/` - Main integration directory
- `/arbitrage/` - Core arbitrage logic modules
- `manifest.json` - Integration metadata (dependencies: mqtt)
- `const.py` - Configuration constants and defaults
- Platform files follow HA naming conventions (`sensor.py`, `switch.py`, etc.)

## Development Tips

- **Timezone handling**: All modules use `utils.py` helper functions for HA timezone conversion
- **Error handling**: Extensive try/catch blocks with fallback to safe defaults
- **Logging**: Uses module-specific loggers (`_LOGGER = logging.getLogger(__name__)`)
- **Data validation**: Input validation via `safe_float()` utility functions
- **MQTT integration**: Price data expected as JSON arrays on configurable topics

## Dependencies

- Home Assistant 2024.1.0+
- MQTT integration (for price data)
- Compatible with Solcast and Solarman integrations
- Designed for Eastern European energy market pricing (PLN currency default)