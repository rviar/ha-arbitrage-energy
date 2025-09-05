import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import mqtt
from homeassistant.components.mqtt import async_publish, async_subscribe

from .const import (
    DOMAIN,
    UPDATE_INTERVAL_SECONDS,
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
        
        update_interval = timedelta(seconds=UPDATE_INTERVAL_SECONDS)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
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
        self._manual_override_until = None

    async def async_setup(self):
        await self._subscribe_mqtt_topics()

    async def _subscribe_mqtt_topics(self):
        buy_topic = self.config.get(CONF_MQTT_BUY_TOPIC, "energy/forecast/buy")
        sell_topic = self.config.get(CONF_MQTT_SELL_TOPIC, "energy/forecast/sell")
        
        try:
            buy_unsub = await async_subscribe(
                self.hass, buy_topic, self._handle_buy_price_message
            )
            sell_unsub = await async_subscribe(
                self.hass, sell_topic, self._handle_sell_price_message
            )
            
            self._mqtt_unsubs = [buy_unsub, sell_unsub]
            _LOGGER.info(f"Subscribed to MQTT topics: {buy_topic}, {sell_topic}")
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to MQTT topics: {e}")

    @callback
    def _handle_buy_price_message(self, message):
        try:
            data = json.loads(message.payload)
            self.price_data["buy_prices"] = data
            self.price_data["last_updated"] = datetime.now()
            _LOGGER.debug(f"Received buy prices: {len(data)} entries")
        except Exception as e:
            _LOGGER.error(f"Error parsing buy price message: {e}")

    @callback
    def _handle_sell_price_message(self, message):
        try:
            data = json.loads(message.payload)
            self.price_data["sell_prices"] = data
            self.price_data["last_updated"] = datetime.now()
            _LOGGER.debug(f"Received sell prices: {len(data)} entries")
        except Exception as e:
            _LOGGER.error(f"Error parsing sell price message: {e}")

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
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
            
            data["today_battery_cycles"] = safe_float(self.hass.states.get(self.config.get(CONF_TODAY_BATTERY_CYCLES_SENSOR)))
            data["total_battery_cycles"] = safe_float(self.hass.states.get(self.config.get(CONF_TOTAL_BATTERY_CYCLES_SENSOR)))
            
            data["price_data"] = self.price_data.copy()
            data["config"] = self.config
            data["options"] = self.options
            
            return data
            
        except Exception as e:
            _LOGGER.error(f"Error collecting sensor data: {e}")
            return {}

    def _get_forecast_data(self, entity_id: str) -> list:
        state = self.hass.states.get(entity_id)
        if not state:
            return []
        
        try:
            if hasattr(state, 'attributes') and 'forecasts' in state.attributes:
                return state.attributes['forecasts']
            return []
        except Exception as e:
            _LOGGER.warning(f"Error getting forecast from {entity_id}: {e}")
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