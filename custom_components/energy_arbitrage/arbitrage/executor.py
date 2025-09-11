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
        
        # Allow 'hold' to always pass through to enforce safe idle state
        if action != 'hold' and not self._can_execute_action():
            _LOGGER.debug("Action execution skipped due to cooldown")
            return False
        
        try:
            success = False
            
            if action == "sell_arbitrage":
                success = await self._execute_sell_arbitrage(decision)
            elif action == "charge_arbitrage":
                success = await self._execute_charge_arbitrage(decision)
            elif action == "hold":
                success = await self._execute_hold(decision)
            else:
                _LOGGER.warning(f"Unknown action: {action}")
                return False
            
            if success:
                # Do not set cooldown for 'hold' to avoid delaying next real action
                if action != 'hold':
                    self._update_last_action_time()
                _LOGGER.info(f"Successfully executed action: {action}")
            else:
                _LOGGER.error(f"Failed to execute action: {action}")
            
            return success
            
        except Exception as e:
            _LOGGER.error(f"Error executing decision {action}: {e}")
            return False

    async def _execute_sell_arbitrage(self, decision: Dict[str, Any]) -> bool:
        """Execute arbitrage sell mode - set inverter for battery discharge/export."""
        try:
            _LOGGER.info(f"Setting inverter for arbitrage selling: target power {decision.get('target_power', 0)}W")
            
            # Set all arbitrage sell parameters
            tasks = []
            
            # 1. Set Work Mode to Export First (prioritize battery discharge)
            tasks.append(self._set_work_mode(WORK_MODE_EXPORT_FIRST))
            
            # 2. Disable Grid Charging (no charging during sell)
            tasks.append(self._set_grid_charging(False))
            
            # 3. Enable Export Surplus (allow energy export to grid)
            tasks.append(self._set_export_surplus(True))
            
            # 4. Set Time of Use to Enabled (use TOU for selling)
            tasks.append(self._set_time_of_use("Enabled"))
            
            # Execute all settings in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            if success_count == total_count:
                _LOGGER.info("Successfully set inverter for arbitrage selling")
                return True
            else:
                _LOGGER.warning(f"Arbitrage sell mode partially set: {success_count}/{total_count} settings successful")
                return success_count > 0  # Return True if at least some settings succeeded
                
        except Exception as e:
            _LOGGER.error(f"Error executing sell arbitrage: {e}")
            return False

    async def _execute_charge_arbitrage(self, decision: Dict[str, Any]) -> bool:
        """Execute arbitrage charge mode - set inverter for grid charging."""
        try:
            _LOGGER.info(f"Setting inverter for arbitrage charging: target power {decision.get('target_power', 0)}W")
            
            # Set all arbitrage charge parameters
            tasks = []
            
            # 1. Enable Grid Charging 
            tasks.append(self._set_grid_charging(True))
            
            # 2. Disable Export Surplus (all energy goes to battery)
            tasks.append(self._set_export_surplus(False))
            
            # 3. Set Time of Use to Disabled (system controls charging)
            tasks.append(self._set_time_of_use("Disabled"))
            
            # Execute all settings in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            if success_count == total_count:
                _LOGGER.info("Successfully set inverter for arbitrage charging")
                return True
            else:
                _LOGGER.warning(f"Arbitrage charge mode partially set: {success_count}/{total_count} settings successful")
                return success_count > 0  # Return True if at least some settings succeeded
                
        except Exception as e:
            _LOGGER.error(f"Error executing charge arbitrage: {e}")
            return False

    async def _execute_hold(self, decision: Dict[str, Any]) -> bool:
        """Execute hold mode - set inverter to autonomous operation."""
        try:
            _LOGGER.info("Setting inverter to autonomous mode (hold)")
            
            # Preflight: if already in desired idle state, skip reapplying settings
            try:
                tou_entity = self.coordinator.config.get('time_of_use_select')
                wm_entity = self.coordinator.config.get('work_mode_select')
                export_entity = self.coordinator.config.get('export_surplus_switch')
                grid_entity = self.coordinator.config.get('battery_grid_charging_switch')

                tou_state = self.coordinator.hass.states.get(tou_entity)
                wm_state = self.coordinator.hass.states.get(wm_entity)
                export_state = self.coordinator.hass.states.get(export_entity)
                grid_state = self.coordinator.hass.states.get(grid_entity)

                tou_ok = tou_state and tou_state.state == "Enabled"
                work_mode_ok = wm_state and wm_state.state == "Zero Export To Load"
                export_ok = export_state and export_state.state == "on"  # enable export surplus
                grid_ok = grid_state and grid_state.state == "off"       # disable grid charging

                if tou_ok and work_mode_ok and export_ok and grid_ok:
                    _LOGGER.debug("Hold preflight: inverter already in idle state; skipping changes")
                    return True
            except Exception:
                # Preflight is best-effort; continue to enforce hold config
                pass

            # Set all hold mode parameters
            tasks = []
            
            # 1. Set Time of Use to Enabled
            tasks.append(self._set_time_of_use("Enabled"))
            
            # 2. Set Work Mode to Zero Export To Load
            tasks.append(self._set_work_mode("Zero Export To Load"))
            
            # 3. Enable Export Surplus
            tasks.append(self._set_export_surplus(True))
            
            # 4. Disable Grid Charging
            tasks.append(self._set_grid_charging(False))
            
            # Execute all settings in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            if success_count == total_count:
                _LOGGER.info("Successfully set inverter to hold mode")
                return True
            else:
                _LOGGER.warning(f"Hold mode partially set: {success_count}/{total_count} settings successful")
                return success_count > 0  # Return True if at least some settings succeeded
                
        except Exception as e:
            _LOGGER.error(f"Error setting hold mode: {e}")
            return False

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

    async def _set_time_of_use(self, option: str) -> bool:
        """Set Time of Use mode (select entity)."""
        try:
            entity_id = self.coordinator.config.get('time_of_use_select')
            if not entity_id:
                _LOGGER.error("Time of Use select entity not configured")
                return False
            
            current_state = self.coordinator.hass.states.get(entity_id)
            if current_state and current_state.state == option:
                _LOGGER.debug(f"Time of Use already set to: {option}")
                return True
            
            await self.coordinator.hass.services.async_call(
                'select', 'select_option',
                {
                    'entity_id': entity_id,
                    'option': option
                }
            )
            
            await asyncio.sleep(2)
            
            new_state = self.coordinator.hass.states.get(entity_id)
            if new_state and new_state.state == option:
                _LOGGER.info(f"Time of Use set to: {option}")
                return True
            else:
                _LOGGER.error(f"Failed to verify Time of Use change to: {option}")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error setting Time of Use to {option}: {e}")
            return False

    async def _set_export_surplus(self, enable: bool) -> bool:
        """Set export surplus switch."""
        try:
            entity_id = self.coordinator.config.get('export_surplus_switch')
            if not entity_id:
                _LOGGER.error("Export surplus switch entity not configured")
                return False
            
            current_state = self.coordinator.hass.states.get(entity_id)
            current_enabled = current_state and current_state.state == "on"
            
            if current_enabled == enable:
                _LOGGER.debug(f"Export surplus already {'enabled' if enable else 'disabled'}")
                return True
            
            service = "turn_on" if enable else "turn_off"
            await self.coordinator.hass.services.async_call(
                'switch', service,
                {'entity_id': entity_id}
            )
            
            await asyncio.sleep(2)
            
            new_state = self.coordinator.hass.states.get(entity_id)
            new_enabled = new_state and new_state.state == "on"
            
            if new_enabled == enable:
                _LOGGER.info(f"Export surplus {'enabled' if enable else 'disabled'}")
                return True
            else:
                _LOGGER.error(f"Failed to verify export surplus state change")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Error setting export surplus to {'on' if enable else 'off'}: {e}")
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
        """Force charge battery - same as arbitrage charging."""
        try:
            _LOGGER.info("Force charging battery to 100% (same as arbitrage charging)")
            
            # Use same settings as arbitrage charging
            tasks = []
            
            # 1. Enable Grid Charging 
            tasks.append(self._set_grid_charging(True))
            
            # 2. Disable Export Surplus (all energy goes to battery)
            tasks.append(self._set_export_surplus(False))
            
            # 3. Set Time of Use to Disabled (system controls charging)
            tasks.append(self._set_time_of_use("Disabled"))
            
            # Execute all settings in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            if success_count == total_count:
                _LOGGER.info("Successfully set inverter for force charging")
                return True
            else:
                _LOGGER.warning(f"Force charge mode partially set: {success_count}/{total_count} settings successful")
                return success_count > 0  # Return True if at least some settings succeeded
                
        except Exception as e:
            _LOGGER.error(f"Error forcing battery charge: {e}")
            return False

    async def stop_force_charge(self) -> bool:
        """Stop force charge - same as hold mode."""
        try:
            _LOGGER.info("Stopping force charge (switching to hold mode)")
            
            # Use same settings as hold mode
            tasks = []
            
            # 1. Set Time of Use to Enabled
            tasks.append(self._set_time_of_use("Enabled"))
            
            # 2. Set Work Mode to Zero Export To Load
            tasks.append(self._set_work_mode("Zero Export To Load"))
            
            # 3. Enable Export Surplus
            tasks.append(self._set_export_surplus(True))
            
            # 4. Disable Grid Charging
            tasks.append(self._set_grid_charging(False))
            
            # Execute all settings in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            if success_count == total_count:
                _LOGGER.info("Successfully stopped force charging (hold mode set)")
                return True
            else:
                _LOGGER.warning(f"Stop force charge partially set: {success_count}/{total_count} settings successful")
                return success_count > 0
                
        except Exception as e:
            _LOGGER.error(f"Error stopping force charge: {e}")
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