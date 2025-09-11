from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
from .arbitrage.utils import get_current_ha_time, format_ha_time, safe_float
from .arbitrage.constants import FALLBACK_BATTERY_CAPACITY_WH
from .arbitrage.predictor import EnergyBalancePredictor
from .arbitrage.sensor_data_helper import SensorDataHelper
from .arbitrage.time_analyzer import TimeWindowAnalyzer
from .arbitrage.constants import MIN_SPREAD_PERCENT, MIN_TRADE_ENERGY_WH, TRADE_COOLDOWN_MINUTES

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfPower, UnitOfEnergy, PERCENTAGE

from .const import DOMAIN, CONF_CURRENCY, DEFAULT_CURRENCY
from .coordinator import EnergyArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EnergyArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        # 🎯 Core decision sensors  
        EnergyArbitrageROISensor(coordinator, entry),
        EnergyArbitrageStatusSensor(coordinator, entry),
        
        
        # 💰 Current pricing
        EnergyArbitrageCurrentBuyPriceSensor(coordinator, entry),
        EnergyArbitrageCurrentSellPriceSensor(coordinator, entry),
        
        # ⚡ System monitoring  
        EnergyArbitrageBatteryLevelSensor(coordinator, entry),
        EnergyArbitragePVPowerSensor(coordinator, entry),
        EnergyArbitrageLoadPowerSensor(coordinator, entry),
        EnergyArbitrageGridPowerSensor(coordinator, entry),
        
        # ☀️ Solar forecasting
        EnergyArbitragePVForecastTodaySensor(coordinator, entry),
        EnergyArbitragePVForecastTomorrowSensor(coordinator, entry),
        
        # 🧠 Predictive intelligence
        EnergyArbitrageEnergyForecastSensor(coordinator, entry),
        EnergyArbitragePriceWindowsSensor(coordinator, entry),
        # Strategic plan sensor removed (planner deprecated)
        EnergyArbitragePolicyDecisionSensor(coordinator, entry),
    ]

    async_add_entities(entities)

class EnergyArbitrageBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry, sensor_type: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_has_entity_name = True
    
    @property
    def currency(self) -> str:
        """Get the configured currency from the entry data."""
        config = self._entry.data
        options = self._entry.options
        # Use already imported constants
        return options.get(CONF_CURRENCY, config.get(CONF_CURRENCY, DEFAULT_CURRENCY))

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Energy Arbitrage",
            "manufacturer": "Custom",
            "model": "Energy Arbitrage System",
            "sw_version": "1.0.0",
        }

class EnergyArbitrageROISensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "roi")
        self._attr_name = "Expected ROI"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:trending-up"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        opportunity = decision.get("opportunity")
        
        if opportunity:
            return round(opportunity.get("roi_percent", 0.0), 2)
        
        return 0.0

class EnergyArbitrageStatusSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "status")
        self._attr_name = "System Status"
        self._attr_icon = "mdi:information"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        
        if self.coordinator.data.get("emergency_mode"):
            return "emergency"
        elif not self.coordinator.data.get("enabled"):
            return "disabled"
        elif self.coordinator.data.get("manual_override_until"):
            return "manual_override"
        else:
            return "active"

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        attrs = {
            "enabled": self.coordinator.data.get("enabled", False),
            "emergency_mode": self.coordinator.data.get("emergency_mode", False),
            "price_data_age": self.coordinator.data.get("price_data_age"),
            # FIXED: Use HA timezone for sensor last update
            "last_update": get_current_ha_time().isoformat(),
        }
        
        manual_override = self.coordinator.data.get("manual_override_until")
        if manual_override:
            attrs["manual_override_until"] = manual_override.isoformat()
        
        return attrs


# DELETED: TodayProfitSensor was just a duplicate of profit_forecast

class EnergyArbitrageCurrentBuyPriceSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_buy_price")
        self._attr_name = "Current Buy Price"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:currency-eur-off"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        # Get current buy price using proper time matching
        current_price = self.coordinator.get_current_buy_price()
        return round(current_price, 4)

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get("price_data", {})
        buy_prices = price_data.get("buy_prices", [])
        
        # Get current entry using proper time matching
        current_entry = self.coordinator._find_current_price_entry(buy_prices)
        
        attrs = {
            "data_source": "mqtt_energy_forecast",
            "update_time": price_data.get("last_updated", "unknown"),
            "prices_count": len(buy_prices),
            "current_timestamp": current_entry.get("start", "unknown"),
            "current_period_end": current_entry.get("end", "unknown"),
        }
        
        # Try to find next price entry
        if current_entry and buy_prices:
            current_start = current_entry.get("start")
            for i, entry in enumerate(buy_prices):
                if entry.get("start") == current_start and i + 1 < len(buy_prices):
                    attrs["next_price"] = buy_prices[i + 1].get("value", 0.0)
                    attrs["next_timestamp"] = buy_prices[i + 1].get("start", "unknown")
                    break
        
        return attrs


# DELETED: MonthlyProfitSensor - was a stub returning 0.0

class EnergyArbitrageCurrentSellPriceSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_sell_price")
        self._attr_name = "Current Sell Price"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:currency-eur"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        # Get current sell price using proper time matching
        current_price = self.coordinator.get_current_sell_price()
        return round(current_price, 4)

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get("price_data", {})
        sell_prices = price_data.get("sell_prices", [])
        
        # Get current entry using proper time matching
        current_entry = self.coordinator._find_current_price_entry(sell_prices)
        
        attrs = {
            "data_source": "mqtt_energy_forecast",
            "update_time": price_data.get("last_updated", "unknown"),
            "prices_count": len(sell_prices),
            "current_timestamp": current_entry.get("start", "unknown"),
            "current_period_end": current_entry.get("end", "unknown"),
        }
        
        # Try to find next price entry
        if current_entry and sell_prices:
            current_start = current_entry.get("start")
            for i, entry in enumerate(sell_prices):
                if entry.get("start") == current_start and i + 1 < len(sell_prices):
                    attrs["next_price"] = sell_prices[i + 1].get("value", 0.0)
                    attrs["next_timestamp"] = sell_prices[i + 1].get("start", "unknown")
                    break
        
        return attrs


class EnergyArbitrageBatteryLevelSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_battery_level")
        self._attr_name = "Input Battery Level"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("battery_level", 0.0)


class EnergyArbitragePVPowerSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_pv_power")
        self._attr_name = "Input PV Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:solar-panel-large"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("pv_power", 0.0)


class EnergyArbitrageLoadPowerSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_load_power")
        self._attr_name = "Input Load Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:home-lightning-bolt"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("load_power", 0.0)


class EnergyArbitrageGridPowerSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_grid_power")
        self._attr_name = "Input Grid Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:transmission-tower"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("grid_power", 0.0)


class EnergyArbitragePVForecastTodaySensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_pv_forecast_today")
        self._attr_name = "Input PV Forecast Today"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_icon = "mdi:weather-sunny"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            _LOGGER.info("PVForecastTodaySensor: No coordinator data")
            return 0.0
        
        # Get the source entity directly - Solcast sensors already contain daily totals
        pv_today_entity = self.coordinator.config.get('pv_forecast_today_sensor')
        if not pv_today_entity:
            _LOGGER.warning("PVForecastTodaySensor: No PV forecast today entity configured")
            return 0.0
            
        state = self.coordinator.hass.states.get(pv_today_entity)
        if not state:
            _LOGGER.warning(f"PVForecastTodaySensor: Entity {pv_today_entity} not found")
            return 0.0
        
        try:
            # Solcast forecast sensors contain daily totals in kWh, convert to Wh
            value = float(state.state) * 1000.0  # Convert kWh to Wh
            _LOGGER.info(f"PVForecastTodaySensor: Using direct value from {pv_today_entity}: {value} Wh (was {state.state} kWh)")
            return round(value, 2)
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"PVForecastTodaySensor: Cannot convert state '{state.state}' to float: {e}")
            return 0.0

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        forecast = self.coordinator.data.get("pv_forecast_today", [])
        if not forecast:
            return {"forecast_points": 0, "status": "No forecast data"}
        
        # Extract power values using the same logic as native_value
        power_values = []
        for entry in forecast:
            if isinstance(entry, dict):
                value = (entry.get('pv_estimate', 0) or 
                        entry.get('pv_estimate_10', 0) or 
                        entry.get('pv_estimate_90', 0) or
                        entry.get('forecast', 0) or
                        entry.get('value', 0) or
                        entry.get('power', 0))
                power_values.append(float(value) if value else 0.0)
            elif isinstance(entry, (int, float)):
                power_values.append(float(entry))
        
        max_power = max(power_values) if power_values else 0
        max_index = power_values.index(max_power) if power_values and max_power > 0 else 0
        
        # Try to get period_end from the max power entry
        peak_hour = ""
        if max_index < len(forecast) and isinstance(forecast[max_index], dict):
            peak_hour = forecast[max_index].get('period_end', '') or forecast[max_index].get('datetime', '') or forecast[max_index].get('time', '')
        
        return {
            "forecast_points": len(forecast),
            "peak_hour": peak_hour,
            "peak_power": round(max_power, 3),
            "total_forecast": round(sum(power_values), 2),
            "data_format": "dict" if forecast and isinstance(forecast[0], dict) else "numeric"
        }


class EnergyArbitragePVForecastTomorrowSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "input_pv_forecast_tomorrow")
        self._attr_name = "Input PV Forecast Tomorrow"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_icon = "mdi:weather-sunny-off"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            _LOGGER.info("PVForecastTomorrowSensor: No coordinator data")
            return 0.0
        
        # Get the source entity directly - Solcast sensors already contain daily totals
        pv_tomorrow_entity = self.coordinator.config.get('pv_forecast_tomorrow_sensor')
        if not pv_tomorrow_entity:
            _LOGGER.warning("PVForecastTomorrowSensor: No PV forecast tomorrow entity configured")
            return 0.0
            
        state = self.coordinator.hass.states.get(pv_tomorrow_entity)
        if not state:
            _LOGGER.warning(f"PVForecastTomorrowSensor: Entity {pv_tomorrow_entity} not found")
            return 0.0
        
        try:
            # Solcast forecast sensors contain daily totals in kWh, convert to Wh
            value = float(state.state) * 1000.0  # Convert kWh to Wh
            _LOGGER.info(f"PVForecastTomorrowSensor: Using direct value from {pv_tomorrow_entity}: {value} Wh (was {state.state} kWh)")
            return round(value, 2)
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"PVForecastTomorrowSensor: Cannot convert state '{state.state}' to float: {e}")
            return 0.0

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        forecast = self.coordinator.data.get("pv_forecast_tomorrow", [])
        if not forecast:
            return {"forecast_points": 0, "status": "No forecast data"}
        
        # Extract power values using the same logic as native_value
        power_values = []
        for entry in forecast:
            if isinstance(entry, dict):
                value = (entry.get('pv_estimate', 0) or 
                        entry.get('pv_estimate_10', 0) or 
                        entry.get('pv_estimate_90', 0) or
                        entry.get('forecast', 0) or
                        entry.get('value', 0) or
                        entry.get('power', 0))
                power_values.append(float(value) if value else 0.0)
            elif isinstance(entry, (int, float)):
                power_values.append(float(entry))
        
        max_power = max(power_values) if power_values else 0
        max_index = power_values.index(max_power) if power_values and max_power > 0 else 0
        
        # Try to get period_end from the max power entry
        peak_hour = ""
        if max_index < len(forecast) and isinstance(forecast[max_index], dict):
            peak_hour = forecast[max_index].get('period_end', '') or forecast[max_index].get('datetime', '') or forecast[max_index].get('time', '')
        
        return {
            "forecast_points": len(forecast),
            "peak_hour": peak_hour,
            "peak_power": round(max_power, 3),
            "total_forecast": round(sum(power_values), 2),
            "data_format": "dict" if forecast and isinstance(forecast[0], dict) else "numeric"
        }


class EnergyArbitrageEnergyForecastSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "energy_forecast")
        self._attr_name = "Energy Forecast"
        self._attr_icon = "mdi:crystal-ball"
        self._attr_state_class = None

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        
        try:
            # Use already imported classes
            
            sensor_helper = SensorDataHelper(self.hass, self.coordinator.entry.entry_id, self.coordinator)
            predictor = EnergyBalancePredictor(sensor_helper)
            
            energy_situation = predictor.get_energy_situation_summary()
            return energy_situation
            
        except Exception as e:
            return f"error"

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        try:
            # Use already imported classes
            
            sensor_helper = SensorDataHelper(self.hass, self.coordinator.entry.entry_id, self.coordinator)
            predictor = EnergyBalancePredictor(sensor_helper)
            
            # Get energy balances
            balances = predictor.calculate_combined_balance()
            
            # Get battery strategy
            # Use already imported safe_float
            battery_level = safe_float(self.hass.states.get(self.coordinator.config.get('battery_level_sensor')))
            battery_capacity = self.coordinator.data.get("battery_capacity", FALLBACK_BATTERY_CAPACITY_WH)
            strategy = predictor.assess_battery_strategy(battery_level, battery_capacity)
            
            return {
                # Today's forecast
                "today_pv_forecast": f"{balances['today'].pv_forecast_wh:.0f}Wh",
                "today_consumption_forecast": f"{balances['today'].consumption_forecast_wh:.0f}Wh", 
                "today_net_balance": f"{balances['today'].net_balance_wh:+.0f}Wh",
                "today_has_surplus": balances['today'].has_surplus,
                
                # Tomorrow's forecast
                "tomorrow_pv_forecast": f"{balances['tomorrow'].pv_forecast_wh:.0f}Wh",
                "tomorrow_consumption_forecast": f"{balances['tomorrow'].consumption_forecast_wh:.0f}Wh",
                "tomorrow_net_balance": f"{balances['tomorrow'].net_balance_wh:+.0f}Wh", 
                "tomorrow_has_surplus": balances['tomorrow'].has_surplus,
                
                # 48h outlook
                "next_48h_net_balance": f"{balances['next_48h'].net_balance_wh:+.0f}Wh",
                
                # Strategy
                "strategy_recommendation": strategy['recommendation'],
                "strategy_reason": strategy['reason'],
                "target_battery_level": f"{strategy['target_battery_level']:.0f}%",
                "strategy_urgency": strategy['urgency'],
                "strategy_confidence": f"{strategy['confidence']*100:.0f}%",
                
                # Status
                "forecast_status": "active" if balances['today'].confidence > 0.5 else "limited"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "unavailable"
            }


class EnergyArbitragePolicyDecisionSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "policy_decision")
        self._attr_name = "Policy Decision"
        self._attr_icon = "mdi:shield-check"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        try:
            if hasattr(self.coordinator, 'optimizer'):
                last = self.coordinator.optimizer.get_last_analysis() or {}
                price_situation = last.get('price_situation', {})
                if price_situation.get('immediate_action'):
                    return price_situation['immediate_action'].get('action', 'hold')
            # Fallback to decision action
            return (self.coordinator.data.get("decision") or {}).get("action", "hold")
        except Exception:
            return "error"

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        try:
            attrs: dict[str, Any] = {}
            decision = self.coordinator.data.get("decision", {})
            attrs["decision_action"] = decision.get("action")
            attrs["decision_reason"] = decision.get("reason")
            attrs["target_power"] = decision.get("target_power")
            attrs["target_battery_level"] = decision.get("target_battery_level")

            # Near-term rebuy context
            last = getattr(self.coordinator, 'optimizer', None).get_last_analysis() if hasattr(self.coordinator, 'optimizer') else {}
            near = (last or {}).get('near_term_rebuy', {})
            attrs["near_term_has_opportunity"] = near.get('has_opportunity', False)
            attrs["near_term_roi_percent"] = round(near.get('roi_percent', 0.0), 2)
            attrs["near_term_lookahead_h"] = near.get('lookahead_hours')
            attrs["near_term_min_upcoming_buy"] = near.get('min_upcoming_buy')
            attrs["current_sell_price"] = near.get('current_sell_price')

            # Price situation
            price_situation = (last or {}).get('price_situation', {})
            if price_situation.get('immediate_action'):
                attrs["immediate_action"] = price_situation['immediate_action'].get('action')
                attrs["immediate_price"] = price_situation['immediate_action'].get('price')
                attrs["immediate_urgency"] = price_situation['immediate_action'].get('urgency')
                attrs["immediate_time_remaining_h"] = price_situation['immediate_action'].get('time_remaining')
            if price_situation.get('next_opportunity'):
                attrs["next_action"] = price_situation['next_opportunity'].get('action')
                attrs["next_price"] = price_situation['next_opportunity'].get('price')
                attrs["next_urgency"] = price_situation['next_opportunity'].get('urgency')
                attrs["next_time_until_h"] = price_situation['next_opportunity'].get('time_until_start')

            # Last trades and policy constants
            if hasattr(self.coordinator, 'optimizer'):
                last_trades = self.coordinator.optimizer.get_last_trades()
                attrs.update({
                    "last_sell_ts": last_trades.get('sell'),
                    "last_buy_ts": last_trades.get('buy')
                })
            attrs.update({
                "min_trade_energy_wh": MIN_TRADE_ENERGY_WH,
                "min_spread_percent": MIN_SPREAD_PERCENT,
                "trade_cooldown_minutes": TRADE_COOLDOWN_MINUTES,
            })

            # Best opportunity snapshot
            if hasattr(self.coordinator, 'optimizer'):
                opps = self.coordinator.optimizer.get_last_opportunities()
                if opps:
                    best = opps[0]
                    attrs.update({
                        "best_roi_percent": round(best.get('roi_percent', 0.0), 2),
                        "best_is_immediate_buy": best.get('is_immediate_buy', False),
                        "best_is_immediate_sell": best.get('is_immediate_sell', False),
                        "best_net_profit_per_kwh": best.get('net_profit_per_kwh', 0.0)
                    })

            return attrs
        except Exception as e:
            return {"error": str(e)}


class EnergyArbitragePriceWindowsSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "price_windows")
        self._attr_name = "Price Windows"
        self._attr_icon = "mdi:clock-time-four-outline"
        self._attr_state_class = None

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "no_data"
        
        try:
            # Use already imported classes
            
            sensor_helper = SensorDataHelper(self.hass, self.coordinator.entry.entry_id, self.coordinator)
            time_analyzer = TimeWindowAnalyzer(sensor_helper)
            
            # Analyze price windows
            price_data = self.coordinator.data.get("price_data", {})
            _LOGGER.debug(f"PriceWindowsSensor: price_data keys={list(price_data.keys())}")
            if "buy_prices" in price_data:
                _LOGGER.debug(f"PriceWindowsSensor: buy_prices count={len(price_data['buy_prices'])}")
            if "sell_prices" in price_data:
                _LOGGER.debug(f"PriceWindowsSensor: sell_prices count={len(price_data['sell_prices'])}")
            
            price_windows = time_analyzer.analyze_price_windows(price_data, 24)
            
            if not price_windows:
                return "no_windows"
            
            # Get current situation
            price_situation = time_analyzer.get_current_price_situation(price_windows)
            
            if price_situation.get('current_opportunities', 0) > 0:
                return "active_opportunity"
            elif price_situation.get('upcoming_opportunities', 0) > 0:
                return "upcoming_opportunity"
            else:
                return "monitoring"
                
        except Exception as e:
            return "error"

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        try:
            # Use already imported classes
            
            sensor_helper = SensorDataHelper(self.hass, self.coordinator.entry.entry_id, self.coordinator)
            time_analyzer = TimeWindowAnalyzer(sensor_helper)
            
            # Analyze price windows  
            price_data = self.coordinator.data.get("price_data", {})
            price_windows = time_analyzer.analyze_price_windows(price_data, 24)
            price_situation = time_analyzer.get_current_price_situation(price_windows)
            
            # 🔧 FIX: Define buy/sell windows before using them
            buy_windows = [w for w in price_windows if w.action == 'buy'][:3]
            sell_windows = [w for w in price_windows if w.action == 'sell'][:3]
            
            attributes = {
                "total_windows": len(price_windows),
                "current_opportunities": price_situation.get('current_opportunities', 0),
                "upcoming_opportunities": price_situation.get('upcoming_opportunities', 0),
                "time_pressure": price_situation.get('time_pressure', 'low'),
                
                # 🚀 NEW: Optimization summary
                "buy_windows_count": len(buy_windows),
                "sell_windows_count": len(sell_windows),
                "optimization_enabled": True,
                "timing_analysis_version": "2.0.0"
            }
            
            # Calculate optimization statistics
            optimized_windows = 0
            total_price_improvement = 0
            for window in price_windows:
                if hasattr(window, 'peak_times') and window.peak_times:
                    optimized_windows += 1
                    if window.action == 'buy' and len(window.peak_times) > 0:
                        # For buying: improvement = how much lower the best price is
                        best_price = window.peak_times[0][1]
                        improvement = (window.price - best_price) / window.price
                        total_price_improvement += improvement
                    elif window.action == 'sell' and len(window.peak_times) > 0:
                        # For selling: improvement = how much higher the best price is
                        best_price = window.peak_times[0][1]
                        improvement = (best_price - window.price) / window.price
                        total_price_improvement += improvement
            
            attributes.update({
                "optimized_windows_count": optimized_windows,
                "optimization_coverage": f"{(optimized_windows / len(price_windows) * 100):.1f}%" if price_windows else "0%",
                "average_price_improvement": f"{(total_price_improvement / optimized_windows * 100):.1f}%" if optimized_windows > 0 else "0%"
            })
            
            # Current opportunity details
            if price_situation.get('immediate_action'):
                immediate = price_situation['immediate_action']
                attributes.update({
                    "current_action": immediate['action'],
                    "current_price": f"{immediate['price']:.4f}",
                    "current_urgency": immediate['urgency'],
                    "time_remaining": f"{immediate['time_remaining']:.1f}h"
                })
            
            # Next opportunity details  
            if price_situation.get('next_opportunity'):
                next_opp = price_situation['next_opportunity']
                attributes.update({
                    "next_action": next_opp['action'],
                    "next_price": f"{next_opp['price']:.4f}",
                    "next_urgency": next_opp['urgency'],
                    "time_until_start": f"{next_opp['time_until_start']:.1f}h",
                    "next_duration": f"{next_opp['duration']:.1f}h"
                })
            
            # Window details (up to 5 most relevant)
            # Note: buy_windows and sell_windows already defined above
            
            for i, window in enumerate(buy_windows):
                # Full timestamp with timezone for debugging
                attributes[f"buy_window_{i+1}_timestamp"] = window.start_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                attributes[f"buy_window_{i+1}_start"] = window.start_time.strftime("%H:%M")
                attributes[f"buy_window_{i+1}_end"] = window.end_time.strftime("%H:%M")
                attributes[f"buy_window_{i+1}_duration"] = f"{window.duration_hours:.1f}h"
                attributes[f"buy_window_{i+1}_price"] = f"{window.price:.4f}"
                attributes[f"buy_window_{i+1}_urgency"] = window.urgency
                
                # 🚀 NEW: Peak times optimization info
                if hasattr(window, 'peak_times') and window.peak_times:
                    peak_times = window.peak_times[:3]  # Top 3 peak times
                    attributes[f"buy_window_{i+1}_peak_count"] = len(peak_times)
                    
                    # Best time (lowest price for buying)
                    best_time, best_price = peak_times[0]
                    attributes[f"buy_window_{i+1}_best_time"] = best_time.strftime("%H:%M")
                    attributes[f"buy_window_{i+1}_best_price"] = f"{best_price:.4f}"
                    attributes[f"buy_window_{i+1}_price_improvement"] = f"{((window.price - best_price) / window.price * 100):.1f}%"
                    
                    # All peak times for detailed view
                    peak_list = []
                    for peak_time, peak_price in peak_times:
                        peak_list.append(f"{peak_time.strftime('%H:%M')}={peak_price:.4f}")
                    attributes[f"buy_window_{i+1}_peak_times"] = ", ".join(peak_list)
                else:
                    attributes[f"buy_window_{i+1}_peak_count"] = 0
                    attributes[f"buy_window_{i+1}_optimization_status"] = "no_peak_data"
                
                if window.is_current:
                    attributes[f"buy_window_{i+1}_status"] = "active"
                elif window.is_upcoming:
                    attributes[f"buy_window_{i+1}_status"] = "upcoming"
                else:
                    attributes[f"buy_window_{i+1}_status"] = "past"
            
            for i, window in enumerate(sell_windows):
                # Full timestamp with timezone for debugging
                attributes[f"sell_window_{i+1}_timestamp"] = window.start_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                attributes[f"sell_window_{i+1}_start"] = window.start_time.strftime("%H:%M")
                attributes[f"sell_window_{i+1}_end"] = window.end_time.strftime("%H:%M")
                attributes[f"sell_window_{i+1}_duration"] = f"{window.duration_hours:.1f}h"
                attributes[f"sell_window_{i+1}_price"] = f"{window.price:.4f}"
                attributes[f"sell_window_{i+1}_urgency"] = window.urgency
                
                # 🚀 NEW: Peak times optimization info
                if hasattr(window, 'peak_times') and window.peak_times:
                    peak_times = window.peak_times[:3]  # Top 3 peak times
                    attributes[f"sell_window_{i+1}_peak_count"] = len(peak_times)
                    
                    # Best time (highest price for selling)
                    best_time, best_price = peak_times[0]
                    attributes[f"sell_window_{i+1}_best_time"] = best_time.strftime("%H:%M")
                    attributes[f"sell_window_{i+1}_best_price"] = f"{best_price:.4f}"
                    attributes[f"sell_window_{i+1}_price_improvement"] = f"{((best_price - window.price) / window.price * 100):.1f}%"
                    
                    # All peak times for detailed view
                    peak_list = []
                    for peak_time, peak_price in peak_times:
                        peak_list.append(f"{peak_time.strftime('%H:%M')}={peak_price:.4f}")
                    attributes[f"sell_window_{i+1}_peak_times"] = ", ".join(peak_list)
                else:
                    attributes[f"sell_window_{i+1}_peak_count"] = 0
                    attributes[f"sell_window_{i+1}_optimization_status"] = "no_peak_data"
                
                if window.is_current:
                    attributes[f"sell_window_{i+1}_status"] = "active"
                elif window.is_upcoming:
                    attributes[f"sell_window_{i+1}_status"] = "upcoming"
                else:
                    attributes[f"sell_window_{i+1}_status"] = "past"
            
            return attributes
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "unavailable"
            }
