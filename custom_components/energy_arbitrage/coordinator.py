import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.components.mqtt as mqtt

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
    DEFAULT_UPDATE_INTERVAL,
    WORK_MODE_EXPORT_FIRST,
    WORK_MODE_ZERO_EXPORT,
)
from .arbitrage.optimizer import ArbitrageOptimizer
from .arbitrage.executor import ArbitrageExecutor
from .arbitrage.utils import safe_float, safe_int

_LOGGER = logging.getLogger(__name__)

class EnergyArbitrageCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.options = entry.options
        
        # Use configured update interval or default
        configured_interval = self.config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        update_interval = timedelta(minutes=configured_interval)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=update_interval,
            always_update=False,  # Avoid unnecessary updates when data hasn't changed
        )
        
        self.optimizer = ArbitrageOptimizer(self)
        self.executor = ArbitrageExecutor(self)
        
        self.price_data = {
            "buy_prices": [],
            "sell_prices": [],
            "last_updated": None
        }
        
        self._mqtt_unsubs = []
        self._enabled = True
        self._emergency_mode = False
        self._force_charge = False
        self._manual_override_until = None

    async def async_setup(self):
        await self._subscribe_mqtt_topics()

    async def _subscribe_mqtt_topics(self):
        buy_topic = self.config.get(CONF_MQTT_BUY_TOPIC, "energy/forecast/buy")
        sell_topic = self.config.get(CONF_MQTT_SELL_TOPIC, "energy/forecast/sell")
        
        try:
            buy_unsub = await mqtt.async_subscribe(
                self.hass, buy_topic, self._handle_buy_price_message
            )
            sell_unsub = await mqtt.async_subscribe(
                self.hass, sell_topic, self._handle_sell_price_message
            )
            
            self._mqtt_unsubs = [buy_unsub, sell_unsub]
            _LOGGER.info(f"Subscribed to MQTT topics: {buy_topic}, {sell_topic}")
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to MQTT topics: {e}")

    @callback
    def _handle_buy_price_message(self, message):
        try:
            _LOGGER.debug(f"Raw buy price message payload: {message.payload}")
            data = json.loads(message.payload)
            _LOGGER.debug(f"Parsed buy price data type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and len(data) > 0:
                _LOGGER.debug(f"First buy price entry: {data[0]}")
            
            self.price_data["buy_prices"] = data
            self.price_data["last_updated"] = datetime.now()
            _LOGGER.debug(f"Stored buy prices: {len(data)} entries")
            # Trigger sensor update with fresh data
            self.hass.async_create_task(self.async_request_refresh())
        except Exception as e:
            _LOGGER.error(f"Error parsing buy price message: {e}")

    @callback
    def _handle_sell_price_message(self, message):
        try:
            _LOGGER.debug(f"Raw sell price message payload: {message.payload}")
            data = json.loads(message.payload)
            _LOGGER.debug(f"Parsed sell price data type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and len(data) > 0:
                _LOGGER.debug(f"First sell price entry: {data[0]}")
            
            self.price_data["sell_prices"] = data
            self.price_data["last_updated"] = datetime.now()
            _LOGGER.debug(f"Stored sell prices: {len(data)} entries")
            # Trigger sensor update with fresh data
            self.hass.async_create_task(self.async_request_refresh())
        except Exception as e:
            _LOGGER.error(f"Error parsing sell price message: {e}")

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            import asyncio
            async with asyncio.timeout(30):  # 30 second timeout for safety
                data = await self._collect_sensor_data()
                
                if not self._enabled or self._emergency_mode:
                    decision = {"action": "hold", "reason": "Disabled or emergency mode"}
                elif self._is_manual_override_active():
                    decision = {"action": "manual_override", "reason": "Manual override active"}
                else:
                    decision = await self.optimizer.calculate_optimal_action(data)
                    if decision["action"] != "hold":
                        await self.executor.execute_decision(decision)
                
                return {
                    **data,
                    "decision": decision,
                    "enabled": self._enabled,
                    "emergency_mode": self._emergency_mode,
                    "force_charge": self._force_charge,
                    "manual_override_until": self._manual_override_until,
                    "price_data_age": self._get_price_data_age(),
                }
        except Exception as e:
            _LOGGER.error(f"Error updating data: {e}")
            raise UpdateFailed(f"Error fetching data: {e}")

    async def _collect_sensor_data(self) -> Dict[str, Any]:
        data = {}
        
        try:
            data["pv_power"] = safe_float(self.hass.states.get(self.config[CONF_PV_POWER_SENSOR]))
            data["battery_level"] = safe_float(self.hass.states.get(self.config[CONF_BATTERY_LEVEL_SENSOR]))
            data["battery_power"] = safe_float(self.hass.states.get(self.config[CONF_BATTERY_POWER_SENSOR]))
            data["load_power"] = safe_float(self.hass.states.get(self.config[CONF_LOAD_POWER_SENSOR]))
            data["grid_power"] = safe_float(self.hass.states.get(self.config[CONF_GRID_POWER_SENSOR]))
            
            data["pv_forecast_today"] = self._get_forecast_data(self.config[CONF_PV_FORECAST_TODAY_SENSOR])
            data["pv_forecast_tomorrow"] = self._get_forecast_data(self.config[CONF_PV_FORECAST_TOMORROW_SENSOR])
            
            work_mode_state = self.hass.states.get(self.config[CONF_WORK_MODE_SELECT])
            data["work_mode"] = work_mode_state.state if work_mode_state else None
            
            charging_state = self.hass.states.get(self.config[CONF_BATTERY_GRID_CHARGING_SWITCH])
            data["grid_charging"] = charging_state.state == "on" if charging_state else False
            
            today_cycles_entity = self.config.get(CONF_TODAY_BATTERY_CYCLES_SENSOR)
            total_cycles_entity = self.config.get(CONF_TOTAL_BATTERY_CYCLES_SENSOR)
            
            today_state = self.hass.states.get(today_cycles_entity)
            total_state = self.hass.states.get(total_cycles_entity)
            
            data["today_battery_cycles"] = safe_float(today_state)
            data["total_battery_cycles"] = safe_float(total_state)
            
            _LOGGER.debug(f"Battery cycles - Today: {today_state.state if today_state else 'None'} ({today_cycles_entity}), Total: {total_state.state if total_state else 'None'} ({total_cycles_entity})")
            
            data["price_data"] = self.price_data.copy()
            data["config"] = self.config
            data["options"] = self.options
            
            # Debug price data structure
            buy_count = len(self.price_data.get("buy_prices", []))
            sell_count = len(self.price_data.get("sell_prices", []))
            _LOGGER.debug(f"Collecting sensor data: buy_prices={buy_count}, sell_prices={sell_count}")
            
            return data
            
        except Exception as e:
            _LOGGER.error(f"Error collecting sensor data: {e}")
            return {}

    def _get_forecast_data(self, entity_id: str) -> list:
        state = self.hass.states.get(entity_id)
        if not state:
            _LOGGER.warning(f"PV forecast entity {entity_id} not found")
            return []
        
        _LOGGER.info(f"=== DEBUGGING PV FORECAST {entity_id} ===")
        _LOGGER.info(f"Entity state: {state.state}")
        _LOGGER.info(f"Entity attributes keys: {list(state.attributes.keys())}")
        
        # Log full attributes for debugging (first 3 items only to avoid spam)
        for i, (key, value) in enumerate(state.attributes.items()):
            if i < 3:
                if isinstance(value, list) and len(value) > 0:
                    _LOGGER.info(f"Attribute '{key}': list with {len(value)} items, first item: {value[0]}")
                else:
                    _LOGGER.info(f"Attribute '{key}': {type(value).__name__} = {value}")
        
        try:
            # Check for different possible attribute names
            forecast_data = None
            found_attribute = None
            
            if 'forecasts' in state.attributes:
                forecast_data = state.attributes['forecasts']
                found_attribute = 'forecasts'
            elif 'detailedForecast' in state.attributes:
                forecast_data = state.attributes['detailedForecast']
                found_attribute = 'detailedForecast'
            elif 'forecast' in state.attributes:
                forecast_data = state.attributes['forecast']
                found_attribute = 'forecast'
            else:
                # Try to get numeric state value directly
                try:
                    numeric_value = float(state.state)
                    _LOGGER.info(f"Using numeric state value: {numeric_value}")
                    # Create a simple forecast entry
                    forecast_data = [{'pv_estimate': numeric_value, 'period_end': 'unknown'}]
                    found_attribute = 'numeric_state'
                except (ValueError, TypeError):
                    _LOGGER.warning(f"No recognized forecast attribute found in {entity_id}. Available: {list(state.attributes.keys())}")
                    return []
            
            if forecast_data and len(forecast_data) > 0:
                _LOGGER.info(f"Using attribute '{found_attribute}' with {len(forecast_data)} entries")
                _LOGGER.info(f"First forecast entry: {forecast_data[0]}")
                
                # Log keys in first few forecast entries
                if isinstance(forecast_data[0], dict):
                    _LOGGER.info(f"Keys in first forecast entry: {list(forecast_data[0].keys())}")
                    # Show first few entries with their values
                    for i, entry in enumerate(forecast_data[:3]):
                        if isinstance(entry, dict):
                            _LOGGER.info(f"Forecast entry {i}: {entry}")
                
                return forecast_data
            else:
                _LOGGER.warning(f"Forecast data is empty for {entity_id}")
                return []
                
        except Exception as e:
            _LOGGER.error(f"Error getting forecast from {entity_id}: {e}")
            import traceback
            _LOGGER.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _get_price_data_age(self) -> Optional[int]:
        if self.price_data["last_updated"]:
            return (datetime.now() - self.price_data["last_updated"]).total_seconds()
        return None

    def _is_manual_override_active(self) -> bool:
        if not self._manual_override_until:
            return False
        return datetime.now() < self._manual_override_until

    async def set_enabled(self, enabled: bool):
        self._enabled = enabled
        await self.async_request_refresh()

    async def set_emergency_mode(self, emergency: bool):
        self._emergency_mode = emergency
        if emergency:
            await self.executor.enter_emergency_mode()
        await self.async_request_refresh()

    async def set_force_charge(self, force_charge: bool):
        self._force_charge = force_charge
        if force_charge:
            await self.executor.force_charge_battery()
        await self.async_request_refresh()

    async def set_manual_override(self, hours: int):
        self._manual_override_until = datetime.now() + timedelta(hours=hours)
        await self.async_request_refresh()

    async def clear_manual_override(self):
        self._manual_override_until = None
        await self.async_request_refresh()

    async def recalculate(self):
        await self.async_request_refresh()

    def __del__(self):
        for unsub in self._mqtt_unsubs:
            if unsub:
                unsub()