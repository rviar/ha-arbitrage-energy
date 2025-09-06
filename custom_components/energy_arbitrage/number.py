"""Number entities for Energy Arbitrage configuration."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberDeviceClass, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_MIN_ARBITRAGE_MARGIN,
    CONF_PLANNING_HORIZON,
    CONF_MAX_DAILY_CYCLES,
    CONF_BATTERY_EFFICIENCY,
    CONF_MIN_BATTERY_RESERVE,
    CONF_MAX_BATTERY_POWER,
    CONF_BATTERY_CAPACITY,
    DEFAULT_MIN_ARBITRAGE_MARGIN,
    DEFAULT_PLANNING_HORIZON,
    DEFAULT_MAX_DAILY_CYCLES,
    DEFAULT_BATTERY_EFFICIENCY,
    DEFAULT_MIN_BATTERY_RESERVE,
    DEFAULT_MAX_BATTERY_POWER,
    DEFAULT_BATTERY_CAPACITY,
)
from .coordinator import EnergyArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EnergyArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        EnergyArbitrageMinArbitrageMarginNumber(coordinator, entry),
        EnergyArbitragePlanningHorizonNumber(coordinator, entry),
        EnergyArbitrageMaxDailyCyclesNumber(coordinator, entry),
        EnergyArbitrageBatteryEfficiencyNumber(coordinator, entry),
        EnergyArbitrageMinBatteryReserveNumber(coordinator, entry),
        EnergyArbitrageMaxBatteryPowerNumber(coordinator, entry),
        EnergyArbitrageBatteryCapacityNumber(coordinator, entry),
    ]

    async_add_entities(entities)


class EnergyArbitrageBaseNumber(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry, config_key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._config_key = config_key
        self._attr_unique_id = f"{entry.entry_id}_{config_key}"
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

    async def async_set_native_value(self, value: float) -> None:
        """Update the configuration value."""
        # Update entry options
        new_options = dict(self._entry.options)
        new_options[self._config_key] = value
        
        self.hass.config_entries.async_update_entry(
            self._entry, options=new_options
        )
        
        # Request coordinator refresh to update sensors
        await self.coordinator.async_request_refresh()


class EnergyArbitrageMinArbitrageMarginNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_MIN_ARBITRAGE_MARGIN)
        self._attr_name = "Min Arbitrage Margin"
        self._attr_icon = "mdi:percent"
        self._attr_native_min_value = 1.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        config = self._entry.data
        options = self._entry.options
        return options.get(self._config_key, config.get(self._config_key, DEFAULT_MIN_ARBITRAGE_MARGIN))


class EnergyArbitragePlanningHorizonNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_PLANNING_HORIZON)
        self._attr_name = "Planning Horizon"
        self._attr_icon = "mdi:clock-outline"
        self._attr_native_min_value = 12
        self._attr_native_max_value = 48
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "h"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> int:
        config = self._entry.data
        options = self._entry.options
        return int(options.get(self._config_key, config.get(self._config_key, DEFAULT_PLANNING_HORIZON)))


class EnergyArbitrageMaxDailyCyclesNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_MAX_DAILY_CYCLES)
        self._attr_name = "Max Daily Cycles"
        self._attr_icon = "mdi:battery-sync"
        self._attr_native_min_value = 0.5
        self._attr_native_max_value = 5.0
        self._attr_native_step = 0.1
        self._attr_native_unit_of_measurement = "cyc"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        config = self._entry.data
        options = self._entry.options
        return options.get(self._config_key, config.get(self._config_key, DEFAULT_MAX_DAILY_CYCLES))


class EnergyArbitrageBatteryEfficiencyNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_BATTERY_EFFICIENCY)
        self._attr_name = "Battery Efficiency"
        self._attr_icon = "mdi:battery-heart-variant"
        self._attr_native_min_value = 70.0
        self._attr_native_max_value = 98.0
        self._attr_native_step = 1.0
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        config = self._entry.data
        options = self._entry.options
        return options.get(self._config_key, config.get(self._config_key, DEFAULT_BATTERY_EFFICIENCY))


class EnergyArbitrageMinBatteryReserveNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_MIN_BATTERY_RESERVE)
        self._attr_name = "Min Battery Reserve"
        self._attr_icon = "mdi:battery-lock"
        self._attr_native_min_value = 10
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> int:
        config = self._entry.data
        options = self._entry.options
        return int(options.get(self._config_key, config.get(self._config_key, DEFAULT_MIN_BATTERY_RESERVE)))


class EnergyArbitrageMaxBatteryPowerNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_MAX_BATTERY_POWER)
        self._attr_name = "Max Battery Power"
        self._attr_device_class = NumberDeviceClass.POWER
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_native_min_value = 1000
        self._attr_native_max_value = 20000
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = "W"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> int:
        config = self._entry.data
        options = self._entry.options
        return int(options.get(self._config_key, config.get(self._config_key, DEFAULT_MAX_BATTERY_POWER)))


class EnergyArbitrageBatteryCapacityNumber(EnergyArbitrageBaseNumber):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CONF_BATTERY_CAPACITY)
        self._attr_name = "Battery Capacity"
        self._attr_device_class = NumberDeviceClass.ENERGY
        self._attr_icon = "mdi:battery-outline"
        self._attr_native_min_value = 5000
        self._attr_native_max_value = 100000
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = "Wh"
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> int:
        config = self._entry.data
        options = self._entry.options
        return int(options.get(self._config_key, config.get(self._config_key, DEFAULT_BATTERY_CAPACITY)))