import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
import zoneinfo
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
    CONF_MIN_ARBITRAGE_DEPTH,
    CONF_SELF_CONSUMPTION_PRIORITY,
    DEFAULT_UPDATE_INTERVAL,
    WORK_MODE_EXPORT_FIRST,
    WORK_MODE_ZERO_EXPORT,
)
from .arbitrage.optimizer import ArbitrageOptimizer
from .arbitrage.executor import ArbitrageExecutor
from .arbitrage.config_manager import ConfigManager
from .arbitrage.exceptions import safe_execute, log_performance
from .arbitrage.utils import safe_float, safe_int, parse_datetime, get_ha_timezone, get_current_ha_time

_LOGGER = logging.getLogger(__name__)

class EnergyArbitrageCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.options = entry.options
        
        # Initialize centralized configuration manager
        self.config_manager = ConfigManager(entry.data)
        
        # Use configured update interval or default (now through config manager)
        system_specs = self.config_manager.get_system_specs()
        update_interval = timedelta(minutes=system_specs.update_interval_minutes)
        
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
        
        # Performance optimization: Cache frequently accessed data
        self._price_cache = {}
        self._price_cache_timeout = 300  # 5 minutes cache timeout

    async def async_setup(self):
        await self._subscribe_mqtt_topics()
        
    # REMOVED: Deprecated _get_current_time_utc method - use HA timezone directly
    
    def _find_current_price_entry(self, price_data: list) -> dict:
        """Find the current price entry based on start/end timestamps using HA timezone."""
        if not price_data:
            return {}
        
        # Use already imported functions
        
        # Get current time in HA timezone 
        ha_tz = get_ha_timezone(self.hass)
        current_time = datetime.now(ha_tz)
        _LOGGER.debug(f"Looking for current price at {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        for entry in price_data:
            try:
                # Parse using the unified function that converts to HA timezone
                start_time = parse_datetime(entry.get('start', ''), self.hass)
                end_time = parse_datetime(entry.get('end', ''), self.hass)
                
                if not start_time or not end_time:
                    _LOGGER.debug(f"Could not parse timestamps in entry: {entry}")
                    continue
                
                _LOGGER.debug(f"Checking period {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
                
                if start_time <= current_time < end_time:
                    _LOGGER.debug(f"Found current period: {entry}")
                    return entry
                    
            except (KeyError, ValueError) as e:
                _LOGGER.debug(f"Invalid price entry format: {e}")
                continue
        
        _LOGGER.warning(f"No current price period found at {current_time.strftime('%H:%M')}, using first entry if available")
        return price_data[0] if price_data else {}
    
    def get_current_buy_price(self) -> float:
        """Get current buy price with proper time matching."""
        buy_prices = self.price_data.get("buy_prices", [])
        current_entry = self._find_current_price_entry(buy_prices)
        return current_entry.get("value", 0.0) or 0.0
    
    def get_current_sell_price(self) -> float:
        """Get current sell price with proper time matching."""
        sell_prices = self.price_data.get("sell_prices", [])
        current_entry = self._find_current_price_entry(sell_prices)
        return current_entry.get("value", 0.0) or 0.0

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
            _LOGGER.info(f"✅ Subscribed to MQTT topics:")
            _LOGGER.info(f"   📊 BUY:  {buy_topic}")
            _LOGGER.info(f"   💰 SELL: {sell_topic}")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to subscribe to MQTT topics: {e}")
            _LOGGER.error(f"   BUY topic: {buy_topic}")  
            _LOGGER.error(f"   SELL topic: {sell_topic}")

    @callback
    def _handle_buy_price_message(self, message):
        try:
            _LOGGER.debug(f"Raw buy price message payload: {message.payload}")
            data = json.loads(message.payload)
            _LOGGER.debug(f"Parsed buy price data type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and len(data) > 0:
                _LOGGER.debug(f"First buy price entry: {data[0]}")
            
            self.price_data["buy_prices"] = data
            # FIXED: Use HA timezone for price data timestamps
            self.price_data["last_updated"] = get_current_ha_time(self.hass)
            _LOGGER.debug(f"Stored buy prices: {len(data)} entries")
            # Trigger sensor update with fresh data
            self.hass.async_create_task(self.async_request_refresh())
        except Exception as e:
            _LOGGER.error(f"Error parsing buy price message: {e}")

    @callback
    def _handle_sell_price_message(self, message):
        try:
            _LOGGER.info(f"🔥 SELL PRICE MESSAGE RECEIVED! Topic: {message.topic}")
            _LOGGER.debug(f"Raw sell price message payload: {message.payload}")
            data = json.loads(message.payload)
            _LOGGER.info(f"✅ Parsed sell price data: type={type(data)}, length={len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and len(data) > 0:
                _LOGGER.info(f"First sell price entry: {data[0]}")
            
            self.price_data["sell_prices"] = data
            # FIXED: Use HA timezone for price data timestamps
            self.price_data["last_updated"] = get_current_ha_time(self.hass)
            _LOGGER.info(f"✅ Stored sell prices: {len(data)} entries")
            # Trigger sensor update with fresh data
            self.hass.async_create_task(self.async_request_refresh())
        except Exception as e:
            _LOGGER.error(f"❌ Error parsing sell price message: {e}")
            _LOGGER.error(f"Message topic: {message.topic}")
            _LOGGER.error(f"Message payload: {message.payload}")

    @safe_execute(default_return={
        "decision": {"action": "hold", "reason": "Update failed - safe mode"},
        "enabled": True,
        "emergency_mode": False,
        "manual_override_until": None,
        "price_data": {"buy_prices": [], "sell_prices": []}
    })
    @log_performance
    async def _async_update_data(self) -> Dict[str, Any]:
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
            
            # Read current values from number entities (UI configurable parameters)
            battery_capacity_entity = f"number.{DOMAIN}_battery_capacity"
            min_reserve_entity = f"number.{DOMAIN}_min_battery_reserve"
            max_power_entity = f"number.{DOMAIN}_max_battery_power"
            planning_horizon_entity = f"number.{DOMAIN}_planning_horizon"
            efficiency_entity = f"number.{DOMAIN}_battery_efficiency"
            min_arbitrage_depth_entity = f"number.{DOMAIN}_min_arbitrage_depth"
            
            battery_capacity_state = self.hass.states.get(battery_capacity_entity)
            min_reserve_state = self.hass.states.get(min_reserve_entity)
            max_power_state = self.hass.states.get(max_power_entity)
            planning_horizon_state = self.hass.states.get(planning_horizon_entity)
            efficiency_state = self.hass.states.get(efficiency_entity)
            min_arbitrage_depth_state = self.hass.states.get(min_arbitrage_depth_entity)
            
            # Use live values from number entities or fallback to config
            data["battery_capacity"] = safe_float(battery_capacity_state) or self.options.get(CONF_BATTERY_CAPACITY, self.config.get(CONF_BATTERY_CAPACITY, 15000))
            data["min_battery_reserve"] = safe_float(min_reserve_state) or self.options.get(CONF_MIN_BATTERY_RESERVE, self.config.get(CONF_MIN_BATTERY_RESERVE, 20.0))
            data["max_battery_power"] = safe_float(max_power_state) or self.options.get(CONF_MAX_BATTERY_POWER, self.config.get(CONF_MAX_BATTERY_POWER, 5000.0))
            data["planning_horizon"] = safe_int(planning_horizon_state) or self.options.get(CONF_PLANNING_HORIZON, self.config.get(CONF_PLANNING_HORIZON, 24))
            data["battery_efficiency"] = safe_float(efficiency_state) or self.options.get(CONF_BATTERY_EFFICIENCY, self.config.get(CONF_BATTERY_EFFICIENCY, 90.0))
            data["min_arbitrage_depth"] = safe_float(min_arbitrage_depth_state) or self.options.get(CONF_MIN_ARBITRAGE_DEPTH, self.config.get(CONF_MIN_ARBITRAGE_DEPTH, 40.0))
            
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
            # FIXED: Use HA timezone for age calculation
            return (get_current_ha_time(self.hass) - self.price_data["last_updated"]).total_seconds()
        return None

    def _is_manual_override_active(self) -> bool:
        if not self._manual_override_until:
            return False
        # FIXED: Use HA timezone for manual override check
        return get_current_ha_time(self.hass) < self._manual_override_until

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
        else:
            await self.executor.stop_force_charge()
        await self.async_request_refresh()

    async def set_manual_override(self, hours: int):
        # FIXED: Use HA timezone for manual override timeout
        self._manual_override_until = get_current_ha_time(self.hass) + timedelta(hours=hours)
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