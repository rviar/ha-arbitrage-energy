from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergyArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EnergyArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        EnergyArbitrageEnabledSwitch(coordinator, entry),
        EnergyArbitrageEmergencyModeSwitch(coordinator, entry),
        EnergyArbitrageForceChargeSwitch(coordinator, entry),
    ]

    async_add_entities(entities)

class EnergyArbitrageBaseSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry, switch_type: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._switch_type = switch_type
        self._attr_unique_id = f"{entry.entry_id}_{switch_type}"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Energy Arbitrage",
            "manufacturer": "Custom",
            "model": "Energy Arbitrage System",
            "sw_version": "1.0.0",
        }

class EnergyArbitrageEnabledSwitch(EnergyArbitrageBaseSwitch):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "enabled")
        self._attr_name = "Arbitrage Enabled"
        self._attr_icon = "mdi:power"

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("enabled", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_enabled(False)

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        return {
            "last_action": self.coordinator.data.get("decision", {}).get("action", "none"),
            "last_reason": self.coordinator.data.get("decision", {}).get("reason", ""),
        }

class EnergyArbitrageEmergencyModeSwitch(EnergyArbitrageBaseSwitch):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "emergency_mode")
        self._attr_name = "Emergency Mode"
        self._attr_icon = "mdi:alert"

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("emergency_mode", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_emergency_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_emergency_mode(False)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "description": "Emergency mode preserves battery and disables arbitrage",
            "work_mode": "Zero Export To Load when active",
        }


class EnergyArbitrageForceChargeSwitch(EnergyArbitrageBaseSwitch):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "force_charge")
        self._attr_name = "Force Charge"
        self._attr_icon = "mdi:battery-charging-100"

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("force_charge", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.set_force_charge(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.set_force_charge(False)

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        config = self.coordinator.data.get("config", {})
        battery_level = self.coordinator.data.get("battery_level", 0)
        
        return {
            "description": "Force charges battery to 100% regardless of price",
            "current_battery_level": f"{battery_level:.1f}%",
            "target_level": "100%",
            "max_charge_power": f"{config.get('max_battery_power', 5000.0)}W"
        }