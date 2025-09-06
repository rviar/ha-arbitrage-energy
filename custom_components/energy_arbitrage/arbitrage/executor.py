import logging
import asyncio
from typing import Dict, Any

from ..const import WORK_MODE_EXPORT_FIRST, WORK_MODE_ZERO_EXPORT

_LOGGER = logging.getLogger(__name__)

class ArbitrageExecutor:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._last_action_time = None
        self._action_cooldown_seconds = 300

    async def execute_decision(self, decision: Dict[str, Any]) -> bool:
        action = decision.get('action', 'hold')
        
        if not self._can_execute_action():
            _LOGGER.debug("Action execution skipped due to cooldown")
            return False
        
        try:
            success = False
            
            if action == "sell_arbitrage":
                success = await self._execute_sell_arbitrage(decision)
            elif action == "charge_arbitrage":
                success = await self._execute_charge_arbitrage(decision)
            elif action == "charge_solar":
                success = await self._execute_charge_solar(decision)
            elif action == "export_solar":
                success = await self._execute_export_solar(decision)
            elif action == "discharge_load":
                success = await self._execute_discharge_load(decision)
            elif action == "hold":
                success = await self._execute_hold(decision)
            else:
                _LOGGER.warning(f"Unknown action: {action}")
                return False
            
            if success:
                self._update_last_action_time()
                _LOGGER.info(f"Successfully executed action: {action}")
            else:
                _LOGGER.error(f"Failed to execute action: {action}")
            
            return success
            
        except Exception as e:
            _LOGGER.error(f"Error executing decision {action}: {e}")
            return False

    async def _execute_sell_arbitrage(self, decision: Dict[str, Any]) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_EXPORT_FIRST)
            await self._set_grid_charging(False)
            
            _LOGGER.info(f"Selling arbitrage: target power {decision.get('target_power', 0)}kW")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error executing sell arbitrage: {e}")
            return False

    async def _execute_charge_arbitrage(self, decision: Dict[str, Any]) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_ZERO_EXPORT)
            await self._set_grid_charging(True)
            
            _LOGGER.info(f"Charging for arbitrage: target power {decision.get('target_power', 0)}kW")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error executing charge arbitrage: {e}")
            return False

    async def _execute_charge_solar(self, decision: Dict[str, Any]) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_ZERO_EXPORT)
            await self._set_grid_charging(False)
            
            _LOGGER.info(f"Charging from solar: target power {decision.get('target_power', 0)}kW")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error executing solar charge: {e}")
            return False

    async def _execute_export_solar(self, decision: Dict[str, Any]) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_EXPORT_FIRST)
            await self._set_grid_charging(False)
            
            _LOGGER.info(f"Exporting solar: target power {decision.get('target_power', 0)}kW")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error executing solar export: {e}")
            return False

    async def _execute_discharge_load(self, decision: Dict[str, Any]) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_ZERO_EXPORT)
            await self._set_grid_charging(False)
            
            _LOGGER.info(f"Discharging for load: target power {decision.get('target_power', 0)}kW")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error executing discharge for load: {e}")
            return False

    async def _execute_hold(self, decision: Dict[str, Any]) -> bool:
        _LOGGER.debug("Holding current state")
        return True

    async def _set_work_mode(self, mode: str) -> bool:
        try:
            work_mode_entity = self.coordinator.config.get('work_mode_select')
            if not work_mode_entity:
                _LOGGER.error("Work mode entity not configured")
                return False
            
            current_state = self.coordinator.hass.states.get(work_mode_entity)
            if current_state and current_state.state == mode:
                _LOGGER.debug(f"Work mode already set to: {mode}")
                return True
            
            await self.coordinator.hass.services.async_call(
                'select', 'select_option',
                {
                    'entity_id': work_mode_entity,
                    'option': mode
                }
            )
            
            await asyncio.sleep(2)
            
            new_state = self.coordinator.hass.states.get(work_mode_entity)
            if new_state and new_state.state == mode:
                _LOGGER.info(f"Work mode set to: {mode}")
                return True
            else:
                _LOGGER.error(f"Failed to verify work mode change to: {mode}")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error setting work mode to {mode}: {e}")
            return False

    async def _set_grid_charging(self, enable: bool) -> bool:
        try:
            grid_charging_entity = self.coordinator.config.get('battery_grid_charging_switch')
            if not grid_charging_entity:
                _LOGGER.error("Grid charging entity not configured")
                return False
            
            current_state = self.coordinator.hass.states.get(grid_charging_entity)
            current_enabled = current_state and current_state.state == "on"
            
            if current_enabled == enable:
                _LOGGER.debug(f"Grid charging already {'enabled' if enable else 'disabled'}")
                return True
            
            service_action = 'turn_on' if enable else 'turn_off'
            
            await self.coordinator.hass.services.async_call(
                'switch', service_action,
                {'entity_id': grid_charging_entity}
            )
            
            await asyncio.sleep(2)
            
            new_state = self.coordinator.hass.states.get(grid_charging_entity)
            new_enabled = new_state and new_state.state == "on"
            
            if new_enabled == enable:
                _LOGGER.info(f"Grid charging {'enabled' if enable else 'disabled'}")
                return True
            else:
                _LOGGER.error(f"Failed to verify grid charging state change")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error setting grid charging to {'on' if enable else 'off'}: {e}")
            return False

    async def enter_emergency_mode(self) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_ZERO_EXPORT)
            await self._set_grid_charging(False)
            
            _LOGGER.warning("Entered emergency mode - preserving battery")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error entering emergency mode: {e}")
            return False

    async def force_charge_battery(self) -> bool:
        try:
            await self._set_work_mode(WORK_MODE_ZERO_EXPORT)
            await self._set_grid_charging(True)
            
            _LOGGER.info("Force charging battery to 100%")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error forcing battery charge: {e}")
            return False

    def _can_execute_action(self) -> bool:
        if self._last_action_time is None:
            return True
        
        import time
        current_time = time.time()
        return (current_time - self._last_action_time) >= self._action_cooldown_seconds

    def _update_last_action_time(self):
        import time
        self._last_action_time = time.time()