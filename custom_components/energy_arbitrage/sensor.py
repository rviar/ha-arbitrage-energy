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
        EnergyArbitrageTotalCyclesSensor(coordinator, entry),
        EnergyArbitrageTodayBatteryCyclesSensor(coordinator, entry),
        EnergyArbitrageNextBuyWindowSensor(coordinator, entry),
        EnergyArbitrageNextSellWindowSensor(coordinator, entry),
        EnergyArbitrageTodayProfitSensor(coordinator, entry),
        EnergyArbitrageMonthlyProfitSensor(coordinator, entry),
        EnergyArbitrageChargeTimeRemainingSensor(coordinator, entry),
        EnergyArbitrageDischargeTimeRemainingSensor(coordinator, entry),
        EnergyArbitragePriceSpreadSensor(coordinator, entry),
        EnergyArbitrageAveragePrice24hSensor(coordinator, entry),
        EnergyArbitrageDegradationCostSensor(coordinator, entry),
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
        from .const import CONF_CURRENCY, DEFAULT_CURRENCY
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
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        currency_icons = {
            "PLN": "mdi:currency-try",
            "EUR": "mdi:currency-eur",
            "USD": "mdi:currency-usd",
            "CZK": "mdi:currency-try",
            "SEK": "mdi:currency-try"
        }
        self._attr_icon = currency_icons.get(currency, "mdi:currency-eur")

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


class EnergyArbitrageDegradationCostSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "degradation_cost")
        self._attr_name = "Battery Degradation Cost"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
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


class EnergyArbitrageTotalCyclesSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "total_cycles")
        self._attr_name = "Total Battery Cycles"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "cycles"
        self._attr_icon = "mdi:battery-heart"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("total_battery_cycles", 0.0)


class EnergyArbitrageTodayBatteryCyclesSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_cycles")
        self._attr_name = "Today Battery Cycles"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "cycles"
        self._attr_icon = "mdi:battery-arrow-up-down"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        return self.coordinator.data.get("today_battery_cycles", 0.0)

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


class EnergyArbitrageNextBuyWindowSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_buy_window")
        self._attr_name = "Next Buy Window"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:cash-minus"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        
        if not buy_prices:
            return None
        
        config = self.coordinator.data.get('config', {})
        planning_horizon = config.get('planning_horizon', 24)
        
        from .arbitrage.utils import find_price_extremes
        low_price_windows = find_price_extremes(buy_prices, planning_horizon, 'valleys')
        
        if low_price_windows:
            next_window = low_price_windows[0]
            return next_window.get('start')
        
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        
        if not buy_prices:
            return {}
        
        config = self.coordinator.data.get('config', {})
        planning_horizon = config.get('planning_horizon', 24)
        
        from .arbitrage.utils import find_price_extremes
        low_price_windows = find_price_extremes(buy_prices, planning_horizon, 'valleys')
        
        if low_price_windows:
            next_window = low_price_windows[0]
            return {
                "price": next_window.get('value', 0),
                "duration": next_window.get('duration', 1),
                "end_time": next_window.get('end', ''),
                "confidence": "high" if len(low_price_windows) > 0 else "low"
            }
        
        return {}


class EnergyArbitrageNextSellWindowSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_sell_window")
        self._attr_name = "Next Sell Window"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:cash-plus"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        
        price_data = self.coordinator.data.get('price_data', {})
        sell_prices = price_data.get('sell_prices', [])
        
        if not sell_prices:
            return None
        
        config = self.coordinator.data.get('config', {})
        planning_horizon = config.get('planning_horizon', 24)
        
        from .arbitrage.utils import find_price_extremes
        high_price_windows = find_price_extremes(sell_prices, planning_horizon, 'peaks')
        
        if high_price_windows:
            next_window = high_price_windows[0]
            return next_window.get('start')
        
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get('price_data', {})
        sell_prices = price_data.get('sell_prices', [])
        
        if not sell_prices:
            return {}
        
        config = self.coordinator.data.get('config', {})
        planning_horizon = config.get('planning_horizon', 24)
        
        from .arbitrage.utils import find_price_extremes
        high_price_windows = find_price_extremes(sell_prices, planning_horizon, 'peaks')
        
        if high_price_windows:
            next_window = high_price_windows[0]
            return {
                "price": next_window.get('value', 0),
                "duration": next_window.get('duration', 1),
                "end_time": next_window.get('end', ''),
                "confidence": "high" if len(high_price_windows) > 0 else "low"
            }
        
        return {}


class EnergyArbitrageTodayProfitSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_profit")
        self._attr_name = "Today Profit"
        self._attr_state_class = SensorStateClass.TOTAL
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:currency-usd"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        # TODO: Implement profit tracking logic
        # This would require storing profit data in coordinator
        decision = self.coordinator.data.get("decision", {})
        current_profit = decision.get("profit_forecast", 0.0)
        
        return round(current_profit, 2)

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        decision = self.coordinator.data.get("decision", {})
        return {
            "last_action": decision.get("action", "hold"),
            "last_profit": decision.get("profit_forecast", 0.0),
            "actions_today": 0,  # TODO: Implement action counting
            "source": "arbitrage_decisions"
        }


class EnergyArbitrageMonthlyProfitSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "monthly_profit")
        self._attr_name = "Monthly Profit"
        self._attr_state_class = SensorStateClass.TOTAL
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:chart-line"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        # TODO: Implement monthly profit tracking
        # This would require persistent storage of profit history
        return 0.0

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        return {
            "days_active": 0,  # TODO: Implement day counting
            "total_actions": 0,  # TODO: Implement action counting  
            "average_daily_profit": 0.0,  # TODO: Calculate average
            "source": "profit_history"
        }


class EnergyArbitrageChargeTimeRemainingSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "charge_time_remaining")
        self._attr_name = "Charge Time Remaining"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:battery-charging"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        
        battery_level = self.coordinator.data.get("battery_level", 0)
        battery_power = self.coordinator.data.get("battery_power", 0)
        config = self.coordinator.data.get("config", {})
        
        battery_capacity = config.get("battery_capacity", 15.0)
        max_battery_power = config.get("max_battery_power", 5.0)
        
        if battery_level >= 95 or battery_power <= 0:
            return 0
        
        remaining_capacity = (95 - battery_level) / 100 * battery_capacity
        charge_power = min(max_battery_power, abs(battery_power) if battery_power > 0 else max_battery_power)
        
        if charge_power > 0:
            hours_remaining = remaining_capacity / charge_power
            return round(hours_remaining * 60, 1)
        
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        battery_level = self.coordinator.data.get("battery_level", 0)
        config = self.coordinator.data.get("config", {})
        
        return {
            "current_battery_level": f"{battery_level:.1f}%",
            "target_level": "95%",
            "charge_power": self.coordinator.data.get("battery_power", 0),
            "max_charge_power": config.get("max_battery_power", 5.0)
        }


class EnergyArbitrageDischargeTimeRemainingSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "discharge_time_remaining")
        self._attr_name = "Discharge Time Remaining"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:battery-arrow-down"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        
        battery_level = self.coordinator.data.get("battery_level", 0)
        load_power = self.coordinator.data.get("load_power", 0)
        pv_power = self.coordinator.data.get("pv_power", 0)
        config = self.coordinator.data.get("config", {})
        
        battery_capacity = config.get("battery_capacity", 15.0)
        min_reserve = config.get("min_battery_reserve", 20)
        
        if battery_level <= min_reserve:
            return 0
        
        available_capacity = (battery_level - min_reserve) / 100 * battery_capacity
        net_consumption = max(0, load_power - pv_power)
        
        if net_consumption > 0:
            hours_remaining = available_capacity / net_consumption
            return round(hours_remaining * 60, 1)
        
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        battery_level = self.coordinator.data.get("battery_level", 0)
        load_power = self.coordinator.data.get("load_power", 0)
        pv_power = self.coordinator.data.get("pv_power", 0)
        config = self.coordinator.data.get("config", {})
        
        return {
            "current_battery_level": f"{battery_level:.1f}%",
            "min_reserve_level": f"{config.get('min_battery_reserve', 20)}%",
            "load_power": f"{load_power:.1f}kW",
            "pv_power": f"{pv_power:.1f}kW",
            "net_consumption": f"{max(0, load_power - pv_power):.1f}kW"
        }


class EnergyArbitragePriceSpreadSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "price_spread")
        self._attr_name = "Price Spread"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:trending-up"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        sell_prices = price_data.get('sell_prices', [])
        
        if not buy_prices or not sell_prices:
            return 0.0
        
        from datetime import datetime, timezone
        from .arbitrage.utils import get_current_price_data
        
        current_time = datetime.now(timezone.utc)
        current_buy = get_current_price_data(buy_prices, current_time)
        current_sell = get_current_price_data(sell_prices, current_time)
        
        if current_buy and current_sell:
            spread = current_sell.get('value', 0) - current_buy.get('value', 0)
            return round(spread, 4)
        
        return 0.0

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        sell_prices = price_data.get('sell_prices', [])
        
        if not buy_prices or not sell_prices:
            return {}
        
        from datetime import datetime, timezone
        from .arbitrage.utils import get_current_price_data
        
        current_time = datetime.now(timezone.utc)
        current_buy = get_current_price_data(buy_prices, current_time)
        current_sell = get_current_price_data(sell_prices, current_time)
        
        if current_buy and current_sell:
            buy_price = current_buy.get('value', 0)
            sell_price = current_sell.get('value', 0)
            spread_percent = ((sell_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
            
            return {
                "current_buy_price": buy_price,
                "current_sell_price": sell_price,
                "spread_percentage": f"{spread_percent:.2f}%",
                "arbitrage_viable": spread_percent > 5.0
            }
        
        return {}


class EnergyArbitrageAveragePrice24hSensor(EnergyArbitrageBaseSensor):
    def __init__(self, coordinator: EnergyArbitrageCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "average_price_24h")
        self._attr_name = "Average Price 24h"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        currency = self.currency
        self._attr_native_unit_of_measurement = currency
        self._attr_icon = "mdi:chart-areaspline"

    @property
    def native_value(self) -> float:
        if not self.coordinator.data:
            return 0.0
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        sell_prices = price_data.get('sell_prices', [])
        
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.debug(f"Average Price 24h: Checking price data - buy_prices: {len(buy_prices)}, sell_prices: {len(sell_prices)}")
        
        # Debug first entries if available
        if buy_prices and len(buy_prices) > 0:
            _LOGGER.debug(f"Average Price 24h: First buy price entry: {buy_prices[0]}")
        if sell_prices and len(sell_prices) > 0:
            _LOGGER.debug(f"Average Price 24h: First sell price entry: {sell_prices[0]}")
        
        if not buy_prices and not sell_prices:
            _LOGGER.debug("Average Price 24h: No price data available")
            return 0.0
        
        from datetime import datetime, timezone, timedelta
        
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time - timedelta(hours=24)
        _LOGGER.debug(f"Average Price 24h: Current time: {current_time}, Cutoff time: {cutoff_time}")
        
        recent_buy_prices = []
        recent_sell_prices = []
        
        for price_entry in buy_prices:
            try:
                entry_time = datetime.fromisoformat(price_entry.get('start', '').replace('Z', '+00:00'))
                if entry_time >= cutoff_time:
                    recent_buy_prices.append(price_entry.get('value', 0))
            except (ValueError, TypeError):
                continue
        
        for price_entry in sell_prices:
            try:
                entry_time = datetime.fromisoformat(price_entry.get('start', '').replace('Z', '+00:00'))
                if entry_time >= cutoff_time:
                    recent_sell_prices.append(price_entry.get('value', 0))
            except (ValueError, TypeError):
                continue
        
        all_prices = recent_buy_prices + recent_sell_prices
        if all_prices:
            average = sum(all_prices) / len(all_prices)
            _LOGGER.debug(f"Average Price 24h: Calculated average {average} from {len(all_prices)} price points")
            return round(average, 4)
        
        _LOGGER.debug("Average Price 24h: No recent price data found within 24h window")
        return 0.0

    @property
    def native_unit_of_measurement(self) -> str:
        return self.currency

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        
        price_data = self.coordinator.data.get('price_data', {})
        buy_prices = price_data.get('buy_prices', [])
        sell_prices = price_data.get('sell_prices', [])
        
        if not buy_prices or not sell_prices:
            return {}
        
        from datetime import datetime, timezone, timedelta
        
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time - timedelta(hours=24)
        
        recent_buy_prices = []
        recent_sell_prices = []
        
        for price_entry in buy_prices:
            try:
                entry_time = datetime.fromisoformat(price_entry.get('start', '').replace('Z', '+00:00'))
                if entry_time >= cutoff_time:
                    recent_buy_prices.append(price_entry.get('value', 0))
            except (ValueError, TypeError):
                continue
        
        for price_entry in sell_prices:
            try:
                entry_time = datetime.fromisoformat(price_entry.get('start', '').replace('Z', '+00:00'))
                if entry_time >= cutoff_time:
                    recent_sell_prices.append(price_entry.get('value', 0))
            except (ValueError, TypeError):
                continue
        
        if recent_buy_prices and recent_sell_prices:
            avg_buy = sum(recent_buy_prices) / len(recent_buy_prices)
            avg_sell = sum(recent_sell_prices) / len(recent_sell_prices)
            min_price = min(min(recent_buy_prices), min(recent_sell_prices))
            max_price = max(max(recent_buy_prices), max(recent_sell_prices))
            
            return {
                "average_buy_price": round(avg_buy, 4),
                "average_sell_price": round(avg_sell, 4),
                "min_price_24h": round(min_price, 4),
                "max_price_24h": round(max_price, 4),
                "price_volatility": f"{((max_price - min_price) / min_price * 100):.1f}%" if min_price > 0 else "0%"
            }
        
        return {}