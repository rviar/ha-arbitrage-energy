import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_PV_POWER_SENSOR,
    CONF_PV_FORECAST_TODAY_SENSOR,
    CONF_PV_FORECAST_TOMORROW_SENSOR,
    CONF_BATTERY_LEVEL_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_LOAD_POWER_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_WORK_MODE_SELECT,
    CONF_BATTERY_GRID_CHARGING_SWITCH,
    CONF_TODAY_BATTERY_CYCLES_SENSOR,
    CONF_TOTAL_BATTERY_CYCLES_SENSOR,
    CONF_MQTT_BUY_TOPIC,
    CONF_MQTT_SELL_TOPIC,
    CONF_MAX_PV_POWER,
    CONF_BATTERY_CAPACITY,
    CONF_MIN_BATTERY_RESERVE,
    CONF_BATTERY_EFFICIENCY,
    CONF_MAX_BATTERY_POWER,
    CONF_PLANNING_HORIZON,
    CONF_UPDATE_INTERVAL,
    CONF_MIN_ARBITRAGE_MARGIN,
    CONF_SELF_CONSUMPTION_PRIORITY,
    CONF_BATTERY_COST,
    CONF_BATTERY_CYCLES,
    CONF_INCLUDE_DEGRADATION,
    CONF_MAX_DAILY_CYCLES,
    CONF_MIN_ARBITRAGE_DEPTH,
    CONF_DEGRADATION_FACTOR,
    DEFAULT_MAX_PV_POWER,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_MIN_BATTERY_RESERVE,
    DEFAULT_BATTERY_EFFICIENCY,
    DEFAULT_MAX_BATTERY_POWER,
    DEFAULT_PLANNING_HORIZON,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_MIN_ARBITRAGE_MARGIN,
    DEFAULT_SELF_CONSUMPTION_PRIORITY,
    DEFAULT_BATTERY_COST,
    DEFAULT_BATTERY_CYCLES,
    DEFAULT_INCLUDE_DEGRADATION,
    DEFAULT_MAX_DAILY_CYCLES,
    DEFAULT_MIN_ARBITRAGE_DEPTH,
    DEFAULT_DEGRADATION_FACTOR,
)

DATA_SCHEMA_SENSORS = vol.Schema({
    vol.Required(CONF_PV_POWER_SENSOR, default="sensor.inverter_pv_power"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_PV_FORECAST_TODAY_SENSOR, default="sensor.solcast_pv_forecast_forecast_today"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_PV_FORECAST_TOMORROW_SENSOR, default="sensor.solcast_pv_forecast_forecast_tomorrow"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_BATTERY_LEVEL_SENSOR, default="sensor.inverter_battery"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_BATTERY_POWER_SENSOR, default="sensor.inverter_battery_power"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_LOAD_POWER_SENSOR, default="sensor.inverter_load_power"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_GRID_POWER_SENSOR, default="sensor.inverter_grid_power"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
})

DATA_SCHEMA_CONTROLS = vol.Schema({
    vol.Required(CONF_WORK_MODE_SELECT, default="select.inverter_work_mode"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="select")
    ),
    vol.Required(CONF_BATTERY_GRID_CHARGING_SWITCH, default="switch.inverter_battery_grid_charging"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="switch")
    ),
    vol.Required(CONF_TODAY_BATTERY_CYCLES_SENSOR, default="sensor.inverter_today_battery_life_cycles"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_TOTAL_BATTERY_CYCLES_SENSOR, default="sensor.inverter_total_battery_life_cycles"): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
})

DATA_SCHEMA_MQTT = vol.Schema({
    vol.Required(CONF_MQTT_BUY_TOPIC, default="energy/forecast/buy"): cv.string,
    vol.Required(CONF_MQTT_SELL_TOPIC, default="energy/forecast/sell"): cv.string,
})

DATA_SCHEMA_SETTINGS = vol.Schema({
    vol.Required(CONF_MAX_PV_POWER, default=DEFAULT_MAX_PV_POWER): vol.Coerce(float),
    vol.Required(CONF_BATTERY_CAPACITY, default=DEFAULT_BATTERY_CAPACITY): vol.Coerce(float),
    vol.Required(CONF_MIN_BATTERY_RESERVE, default=DEFAULT_MIN_BATTERY_RESERVE): vol.Range(min=0, max=100),
    vol.Required(CONF_BATTERY_EFFICIENCY, default=DEFAULT_BATTERY_EFFICIENCY): vol.Range(min=0, max=100),
    vol.Required(CONF_MAX_BATTERY_POWER, default=DEFAULT_MAX_BATTERY_POWER): vol.Coerce(float),
    vol.Required(CONF_PLANNING_HORIZON, default=DEFAULT_PLANNING_HORIZON): vol.Range(min=1, max=48),
    vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.Range(min=1, max=60),
    vol.Required(CONF_MIN_ARBITRAGE_MARGIN, default=DEFAULT_MIN_ARBITRAGE_MARGIN): vol.Range(min=0, max=100),
    vol.Required(CONF_SELF_CONSUMPTION_PRIORITY, default=DEFAULT_SELF_CONSUMPTION_PRIORITY): cv.boolean,
})

DATA_SCHEMA_DEGRADATION = vol.Schema({
    vol.Required(CONF_INCLUDE_DEGRADATION, default=DEFAULT_INCLUDE_DEGRADATION): cv.boolean,
    vol.Required(CONF_BATTERY_COST, default=DEFAULT_BATTERY_COST): vol.Coerce(float),
    vol.Required(CONF_BATTERY_CYCLES, default=DEFAULT_BATTERY_CYCLES): vol.All(vol.Coerce(int), vol.Range(min=1000, max=20000)),
    vol.Required(CONF_MAX_DAILY_CYCLES, default=DEFAULT_MAX_DAILY_CYCLES): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10.0)),
    vol.Required(CONF_MIN_ARBITRAGE_DEPTH, default=DEFAULT_MIN_ARBITRAGE_DEPTH): vol.Range(min=20, max=80),
    vol.Required(CONF_DEGRADATION_FACTOR, default=DEFAULT_DEGRADATION_FACTOR): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=3.0)),
})

class EnergyArbitrageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.data = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_controls()

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_SENSORS,
            description_placeholders={
                "description": "Configure your solar and energy sensors"
            }
        )

    async def async_step_controls(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_mqtt()

        return self.async_show_form(
            step_id="controls",
            data_schema=DATA_SCHEMA_CONTROLS,
            description_placeholders={
                "description": "Configure your inverter control entities"
            }
        )

    async def async_step_mqtt(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_settings()

        return self.async_show_form(
            step_id="mqtt",
            data_schema=DATA_SCHEMA_MQTT,
            description_placeholders={
                "description": "Configure MQTT topics for energy prices"
            }
        )

    async def async_step_settings(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_degradation()

        return self.async_show_form(
            step_id="settings",
            data_schema=DATA_SCHEMA_SETTINGS,
            description_placeholders={
                "description": "Configure system parameters and arbitrage settings"
            }
        )

    async def async_step_degradation(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return self.async_create_entry(
                title="Energy Arbitrage",
                data=self.data
            )

        return self.async_show_form(
            step_id="degradation",
            data_schema=DATA_SCHEMA_DEGRADATION,
            description_placeholders={
                "description": "Configure battery degradation and cycle protection settings"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EnergyArbitrageOptionsFlowHandler(config_entry)

class EnergyArbitrageOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_MIN_BATTERY_RESERVE,
                    default=options.get(CONF_MIN_BATTERY_RESERVE, DEFAULT_MIN_BATTERY_RESERVE)
                ): vol.Range(min=0, max=100),
                vol.Optional(
                    CONF_MIN_ARBITRAGE_MARGIN,
                    default=options.get(CONF_MIN_ARBITRAGE_MARGIN, DEFAULT_MIN_ARBITRAGE_MARGIN)
                ): vol.Range(min=0, max=100),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): vol.Range(min=1, max=60),
                vol.Optional(
                    CONF_SELF_CONSUMPTION_PRIORITY,
                    default=options.get(CONF_SELF_CONSUMPTION_PRIORITY, DEFAULT_SELF_CONSUMPTION_PRIORITY)
                ): cv.boolean,
            })
        )