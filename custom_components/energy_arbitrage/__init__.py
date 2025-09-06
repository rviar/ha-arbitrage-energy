import asyncio
import logging
from datetime import timedelta
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import Platform
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, WORK_MODE_EXPORT_FIRST, WORK_MODE_ZERO_EXPORT
from .coordinator import EnergyArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
]

SERVICE_RECALCULATE = "recalculate"
SERVICE_SET_BATTERY_RESERVE = "set_battery_reserve"
SERVICE_MANUAL_OVERRIDE = "manual_override"
SERVICE_CLEAR_MANUAL_OVERRIDE = "clear_manual_override"
SERVICE_FORCE_WORK_MODE = "force_work_mode"
SERVICE_FORCE_GRID_CHARGING = "force_grid_charging"
SERVICE_HEALTH_CHECK = "health_check"

SERVICE_RECALCULATE_SCHEMA = vol.Schema({})

SERVICE_SET_BATTERY_RESERVE_SCHEMA = vol.Schema({
    vol.Required("reserve_percent"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
})

SERVICE_MANUAL_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("hours"): vol.All(vol.Coerce(int), vol.Range(min=1, max=48))
})

SERVICE_CLEAR_MANUAL_OVERRIDE_SCHEMA = vol.Schema({})

SERVICE_FORCE_WORK_MODE_SCHEMA = vol.Schema({
    vol.Required("work_mode"): vol.In([WORK_MODE_EXPORT_FIRST, WORK_MODE_ZERO_EXPORT]),
    vol.Optional("duration_minutes", default=60): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440))
})

SERVICE_FORCE_GRID_CHARGING_SCHEMA = vol.Schema({
    vol.Required("enable"): cv.boolean,
    vol.Optional("duration_minutes", default=60): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440))
})

SERVICE_HEALTH_CHECK_SCHEMA = vol.Schema({})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    coordinator = EnergyArbitrageCoordinator(hass, entry)
    
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    async def handle_recalculate(call: ServiceCall):
        await coordinator.recalculate()

    async def handle_set_battery_reserve(call: ServiceCall):
        reserve_percent = call.data["reserve_percent"]
        options = dict(entry.options)
        options["min_battery_reserve"] = reserve_percent
        hass.config_entries.async_update_entry(entry, options=options)
        await coordinator.async_request_refresh()

    async def handle_manual_override(call: ServiceCall):
        hours = call.data["hours"]
        await coordinator.set_manual_override(hours)

    async def handle_clear_manual_override(call: ServiceCall):
        await coordinator.clear_manual_override()

    async def handle_force_work_mode(call: ServiceCall):
        work_mode = call.data["work_mode"]
        duration = call.data["duration_minutes"]
        
        await coordinator.executor._set_work_mode(work_mode)
        await coordinator.set_manual_override(duration / 60.0)

    async def handle_force_grid_charging(call: ServiceCall):
        enable = call.data["enable"]
        duration = call.data["duration_minutes"]
        
        await coordinator.executor._set_grid_charging(enable)
        await coordinator.set_manual_override(duration / 60.0)

    async def handle_health_check(call: ServiceCall):
        """Perform a health check of the Energy Arbitrage system."""
        status = {
            "integration_loaded": True,
            "coordinator_data": coordinator.data is not None,
            "mqtt_connected": bool(coordinator._mqtt_unsubs),
            "sensors_available": len([s for s in hass.states.async_all() if s.entity_id.startswith("sensor.energy_arbitrage_")]),
            "last_update": coordinator.last_update_time.isoformat() if coordinator.last_update_time else None,
        }
        
        # Check if sensors have data
        if coordinator.data:
            status.update({
                "battery_level": coordinator.data.get("battery_level"),
                "pv_power": coordinator.data.get("pv_power"),
                "decision_action": coordinator.data.get("decision", {}).get("action"),
                "price_data_available": bool(coordinator.data.get("price_data")),
            })
        
        _LOGGER.info(f"Energy Arbitrage Health Check: {status}")
        
        # Send persistent notification
        hass.components.persistent_notification.async_create(
            f"🔋 **Energy Arbitrage Health Check**\n\n"
            f"✅ Integration loaded: {status['integration_loaded']}\n"
            f"📊 Coordinator data: {status['coordinator_data']}\n" 
            f"📡 MQTT connected: {status['mqtt_connected']}\n"
            f"🎛️ Sensors available: {status['sensors_available']}\n"
            f"🔋 Battery level: {status.get('battery_level', 'N/A')}%\n"
            f"☀️ PV power: {status.get('pv_power', 'N/A')} kW\n"
            f"⚡ Current decision: {status.get('decision_action', 'N/A')}\n"
            f"💰 Price data: {'Available' if status.get('price_data_available') else 'Missing'}\n"
            f"🕐 Last update: {status.get('last_update', 'Never')}",
            title="Energy Arbitrage Status",
            notification_id="energy_arbitrage_health"
        )

    hass.services.async_register(
        DOMAIN, SERVICE_RECALCULATE, handle_recalculate, SERVICE_RECALCULATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BATTERY_RESERVE, handle_set_battery_reserve, SERVICE_SET_BATTERY_RESERVE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MANUAL_OVERRIDE, handle_manual_override, SERVICE_MANUAL_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_MANUAL_OVERRIDE, handle_clear_manual_override, SERVICE_CLEAR_MANUAL_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_WORK_MODE, handle_force_work_mode, SERVICE_FORCE_WORK_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_GRID_CHARGING, handle_force_grid_charging, SERVICE_FORCE_GRID_CHARGING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_HEALTH_CHECK, handle_health_check, SERVICE_HEALTH_CHECK_SCHEMA
    )
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
        hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)
        hass.services.async_remove(DOMAIN, SERVICE_SET_BATTERY_RESERVE)
        hass.services.async_remove(DOMAIN, SERVICE_MANUAL_OVERRIDE)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_MANUAL_OVERRIDE)
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_WORK_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_GRID_CHARGING)
        hass.services.async_remove(DOMAIN, SERVICE_HEALTH_CHECK)
    
    return unload_ok