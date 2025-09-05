from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
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
        EnergyArbitrageStrategySelect(coordinator, entry),
    ]

    async_add_entities(entities)

class EnergyArbitrageStrategySelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_strategy"
        self._attr_name = "Arbitrage Strategy"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:strategy"
        
        self._attr_options = [
            "aggressive",
            "balanced", 
            "conservative",
            "solar_priority",
            "custom"
        ]
        
        self._current_option = "balanced"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Energy Arbitrage",
            "manufacturer": "Custom",
            "model": "Energy Arbitrage System",
            "sw_version": "1.0.0",
        }

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        if option in self.options:
            self._current_option = option
            await self.coordinator.async_request_refresh()
            _LOGGER.info(f"Strategy changed to: {option}")

    @property
    def extra_state_attributes(self) -> dict:
        strategy_descriptions = {
            "aggressive": "Maximum ROI, higher risks, frequent battery cycles",
            "balanced": "Moderate ROI, balanced risks, optimal battery preservation",
            "conservative": "Lower ROI, minimal risks, battery preservation priority",
            "solar_priority": "Self-consumption priority, sell excess only",
            "custom": "User-defined parameters from options"
        }
        
        return {
            "description": strategy_descriptions.get(self._current_option, "Unknown strategy"),
            "available_strategies": list(strategy_descriptions.keys()),
        }