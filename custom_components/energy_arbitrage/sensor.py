from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfPower, UnitOfEnergy, PERCENTAGE

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
        EnergyArbitrageNextActionSensor(coordinator, entry),
        EnergyArbitrageTargetPowerSensor(coordinator, entry),
        EnergyArbitrageProfitForecastSensor(coordinator, entry),
        EnergyArbitrageBatteryTargetSensor(coordinator, entry),
        EnergyArbitrageROISensor(coordinator, entry),
        EnergyArbitrageStatusSensor(coordinator, entry),
        EnergyArbitrageDailyCyclesSensor(coordinator, entry),
        EnergyArbitrageTotalCyclesSensor(coordinator, entry),
        EnergyArbitrageDegradationCostSensor(coordinator, entry),
        EnergyArbitrageEquivalentCyclesSensor(coordinator, entry),
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
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Energy Arbitrage",
            "manufacturer": "Custom",
            "model": "Energy Arbitrage System",
            "sw_version": "1.0.0",
        }

class EnergyArbitrageNextActionSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_action")
        self._attr_name = "Next Action"
        self._attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        
        decision = self.coordinator.data.get("decision", {})
        return decision.get("action", "unknown")

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        decision = self.coordinator.data.get("decision", {})
        opportunity = decision.get("opportunity")
        
        attrs = {
            "reason": decision.get("reason", ""),
            "target_power": decision.get("target_power", 0),
            "profit_forecast": decision.get("profit_forecast", 0),
        }
        
        if opportunity:
            attrs.update({
                "opportunity_roi": opportunity.get("roi_percent", 0),
                "opportunity_buy_price": opportunity.get("buy_price", 0),
                "opportunity_sell_price": opportunity.get("sell_price", 0),
            })
        
        return attrs

class EnergyArbitrageTargetPowerSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "target_power")
        self._attr_name = "Target Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_icon = "mdi:flash"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        return decision.get("target_power", 0.0)

class EnergyArbitrageProfitForecastSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "profit_forecast")
        self._attr_name = "Profit Forecast"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_icon = "mdi:currency-eur"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        return round(decision.get("profit_forecast", 0.0), 4)

class EnergyArbitrageBatteryTargetSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "battery_target")
        self._attr_name = "Battery Target Level"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        target = decision.get("target_battery_level")
        return round(target, 1) if target is not None else 0.0

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
            "last_update": datetime.now().isoformat(),
        }
        
        manual_override = self.coordinator.data.get("manual_override_until")
        if manual_override:
            attrs["manual_override_until"] = manual_override.isoformat()
        
        return attrs

class EnergyArbitrageDailyCyclesSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "daily_cycles")
        self._attr_name = "Daily Battery Cycles"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "cycles"
        self._attr_icon = "mdi:battery-sync"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        return round(decision.get("daily_cycles", 0.0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        decision = self.coordinator.data.get("decision", {})
        return {
            "remaining_cycles": decision.get("remaining_cycles", 0.0),
            "max_daily_cycles": decision.get("max_cycles", 2.0),
            "total_cycles": decision.get("total_cycles", 0.0),
            "source": "inverter_sensor",
        }

class EnergyArbitrageDegradationCostSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "degradation_cost")
        self._attr_name = "Battery Degradation Cost"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "EUR"
        self._attr_icon = "mdi:battery-minus"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        opportunity = decision.get("opportunity")
        
        if opportunity:
            return round(opportunity.get("degradation_cost", 0.0), 4)
        
        return 0.0

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        decision = self.coordinator.data.get("decision", {})
        opportunity = decision.get("opportunity")
        
        if opportunity:
            return {
                "cost_per_cycle": opportunity.get("cost_per_cycle", 0.0),
                "depth_of_discharge": opportunity.get("depth_of_discharge", 0.0),
                "equivalent_cycles": opportunity.get("equivalent_cycles", 0.0),
            }
        
        return {}

class EnergyArbitrageEquivalentCyclesSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "equivalent_cycles")
        self._attr_name = "Equivalent Battery Cycles"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "cycles"
        self._attr_icon = "mdi:battery-arrow-down"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        decision = self.coordinator.data.get("decision", {})
        opportunity = decision.get("opportunity")
        
        if opportunity:
            return round(opportunity.get("equivalent_cycles", 0.0), 4)
        
        return 0.0

class EnergyArbitrageTotalCyclesSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "total_cycles")
        self._attr_name = "Total Battery Cycles"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = "cycles"
        self._attr_icon = "mdi:battery-heart"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("total_battery_cycles", 0.0)

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        config = self.coordinator.data.get("config", {})
        options = self.coordinator.data.get("options", {})
        
        rated_cycles = options.get('battery_cycles', config.get('battery_cycles', 6000))
        total_cycles = self.coordinator.data.get("total_battery_cycles", 0.0)
        
        remaining_cycles = max(0, rated_cycles - total_cycles)
        health_percent = max(0, min(100, ((rated_cycles - total_cycles) / rated_cycles) * 100))
        
        return {
            "rated_cycles": rated_cycles,
            "remaining_cycles": remaining_cycles,
            "battery_health": f"{health_percent:.1f}%",
            "source": "inverter_sensor",
        }