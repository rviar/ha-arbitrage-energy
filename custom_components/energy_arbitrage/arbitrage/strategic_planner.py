"""
Strategic Planner for long-term arbitrage planning.
Combines energy forecasts, price windows, and system constraints into optimal strategies.
"""

import logging
from datetime import datetime, timezone, timedelta
from .utils import get_current_ha_time, get_ha_timezone, convert_utc_to_ha_time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

_LOGGER = logging.getLogger(__name__)

class OperationType(Enum):
    """Types of planned operations."""
    CHARGE_URGENT = "charge_urgent"      # Critical charging needed
    CHARGE_OPTIMAL = "charge_optimal"    # Optimal charging opportunity
    SELL_URGENT = "sell_urgent"          # Critical selling needed
    SELL_OPTIMAL = "sell_optimal"        # Optimal selling opportunity
    HOLD_PRESERVE = "hold_preserve"      # Hold to preserve energy
    HOLD_WAIT = "hold_wait"              # Hold waiting for better opportunity

@dataclass
class PlannedOperation:
    """A planned battery operation with full context."""
    operation_type: OperationType
    start_time: datetime
    end_time: datetime
    target_energy_wh: float
    target_power_w: float
    expected_price: float
    confidence: float                    # 0-1 confidence in this plan
    priority: int                       # 1-5, where 1 is highest priority
    reason: str                         # Human-readable explanation
    dependencies: List[str]             # IDs of operations this depends on
    alternatives: List['PlannedOperation']  # Alternative operations if this fails
    
    @property
    def duration_hours(self) -> float:
        """Duration of the operation in hours."""
        return (self.end_time - self.start_time).total_seconds() / 3600
    
    @property
    def operation_id(self) -> str:
        """Unique ID for this operation."""
        return f"{self.operation_type.value}_{self.start_time.strftime('%H%M')}"
    
    @property
    def is_active_now(self) -> bool:
        """True if this operation should be active right now."""
        # FIXED: Use HA timezone for operation status checks
        now = get_current_ha_time()
        return self.start_time <= now <= self.end_time
    
    @property
    def starts_soon(self) -> bool:
        """True if this operation starts within the next hour."""
        # FIXED: Use HA timezone for upcoming operation checks
        now = get_current_ha_time()
        return now <= self.start_time <= now + timedelta(hours=1)

@dataclass
class StrategicPlan:
    """A comprehensive strategic plan for the next 24-48 hours."""
    plan_id: str
    created_at: datetime
    valid_until: datetime
    operations: List[PlannedOperation]
    expected_profit: float
    risk_assessment: str               # "low", "medium", "high"
    scenario: str                      # Description of the scenario this plan addresses
    confidence: float                  # Overall confidence in the plan
    fallback_plan: Optional['StrategicPlan']  # Fallback if main plan fails
    
    @property
    def active_operations(self) -> List[PlannedOperation]:
        """Operations that should be active right now."""
        return [op for op in self.operations if op.is_active_now]
    
    @property
    def upcoming_operations(self) -> List[PlannedOperation]:
        """Operations starting soon."""
        return [op for op in self.operations if op.starts_soon]
    
    @property
    def next_operation(self) -> Optional[PlannedOperation]:
        """The next operation in chronological order."""
        # FIXED: Use HA timezone for plan validity checks
        now = get_current_ha_time()
        future_ops = [op for op in self.operations if op.start_time > now]
        return min(future_ops, key=lambda op: op.start_time) if future_ops else None


class StrategicPlanner:
    """Creates and manages long-term strategic plans for energy arbitrage."""
    
    def __init__(self, sensor_helper, energy_predictor, time_analyzer):
        self.sensor_helper = sensor_helper
        self.energy_predictor = energy_predictor
        self.time_analyzer = time_analyzer
        self._current_plan: Optional[StrategicPlan] = None
        self._plan_history: List[StrategicPlan] = []
        
    def create_comprehensive_plan(self, 
                                current_battery_level: float,
                                battery_capacity_wh: float,
                                max_power_w: float,
                                price_data: Dict[str, Any],
                                planning_horizon_hours: int = 48,
                                currency: str = "PLN") -> StrategicPlan:
        """Create a comprehensive strategic plan."""
        
        try:
            # Get energy balance forecast
            energy_balances = self.energy_predictor.calculate_combined_balance()
            energy_strategy = self.energy_predictor.assess_battery_strategy(current_battery_level, battery_capacity_wh)
            
            # Get price windows
            price_windows = self.time_analyzer.analyze_price_windows(price_data, planning_horizon_hours)
            
            # Determine the primary scenario
            scenario = self._identify_scenario(energy_balances, energy_strategy, price_windows)
            
            # Create operations based on scenario
            operations = self._create_scenario_operations(
                scenario, energy_balances, energy_strategy, price_windows,
                current_battery_level, battery_capacity_wh, max_power_w
            )
            
            # Optimize operation sequence
            operations = self._optimize_operation_sequence(operations, current_battery_level, battery_capacity_wh)
            
            # Calculate expected profit
            expected_profit = self._calculate_plan_profit(operations)
            
            # Assess risk
            risk_assessment = self._assess_plan_risk(operations, energy_balances)
            
            # Create the plan
            # Use HA timezone for strategic planning
            # Use already imported get_ha_timezone
            ha_tz = get_ha_timezone(getattr(self.sensor_helper, 'hass', None))
            now = datetime.now(ha_tz)
            
            plan = StrategicPlan(
                plan_id=f"plan_{now.strftime('%Y%m%d_%H%M%S')}",
                created_at=now,
                valid_until=now + timedelta(hours=planning_horizon_hours),
                operations=operations,
                expected_profit=expected_profit,
                risk_assessment=risk_assessment,
                scenario=scenario,
                confidence=min([op.confidence for op in operations] + [1.0]),
                fallback_plan=None  # Will be created if needed
            )
            
            # Create fallback plan for high-risk scenarios
            if risk_assessment == "high":
                plan.fallback_plan = self._create_fallback_plan(plan, current_battery_level, battery_capacity_wh, max_power_w)
            
            # Store the plan
            self._current_plan = plan
            self._plan_history.append(plan)
            
            # Keep only last 5 plans
            if len(self._plan_history) > 5:
                self._plan_history = self._plan_history[-5:]
            
            _LOGGER.info(f"🎯 Strategic plan created: {scenario} ({len(operations)} operations, profit: {currency} {expected_profit:.2f})")
            
            return plan
            
        except Exception as e:
            _LOGGER.error(f"Error creating strategic plan: {e}")
            # Return a basic hold plan
            return self._create_emergency_plan(current_battery_level, battery_capacity_wh)
    
    def _identify_scenario(self, energy_balances, energy_strategy, price_windows) -> str:
        """Identify the primary scenario for planning."""
        
        today_balance = energy_balances['today']
        tomorrow_balance = energy_balances['tomorrow']
        next_48h_balance = energy_balances['next_48h']
        
        buy_windows = [w for w in price_windows if w.action == 'buy']
        sell_windows = [w for w in price_windows if w.action == 'sell']
        
        # Critical scenarios (high priority)
        if energy_strategy['urgency'] == 'high':
            if energy_strategy['recommendation'] in ['charge_aggressive', 'charge_moderate']:
                return f"energy_critical_deficit_{len(buy_windows)}_buy_windows"
            elif energy_strategy['recommendation'] in ['sell_aggressive', 'sell_partial']:
                return f"energy_critical_surplus_{len(sell_windows)}_sell_windows"
        
        # Balanced scenarios (medium priority)
        if today_balance.has_surplus and tomorrow_balance.has_surplus:
            return f"energy_surplus_both_days_{len(sell_windows)}_sell_opportunities"
        elif not today_balance.has_surplus and not tomorrow_balance.has_surplus:
            return f"energy_deficit_both_days_{len(buy_windows)}_buy_opportunities"
        elif today_balance.has_surplus and not tomorrow_balance.has_surplus:
            return f"energy_surplus_today_deficit_tomorrow_{len(buy_windows)}_prep_windows"
        elif not today_balance.has_surplus and tomorrow_balance.has_surplus:
            return f"energy_deficit_today_surplus_tomorrow_{len(sell_windows)}_recovery_windows"
        
        # Price-driven scenarios (low priority)
        if len(buy_windows) > len(sell_windows):
            return f"price_driven_buying_{len(buy_windows)}_opportunities"
        elif len(sell_windows) > len(buy_windows):
            return f"price_driven_selling_{len(sell_windows)}_opportunities"
        
        # Default scenario
        return f"balanced_monitoring_{len(price_windows)}_total_windows"
    
    def _create_scenario_operations(self, 
                                  scenario: str,
                                  energy_balances,
                                  energy_strategy,
                                  price_windows,
                                  current_battery_level: float,
                                  battery_capacity_wh: float,
                                  max_power_w: float) -> List[PlannedOperation]:
        """Create operations based on the identified scenario."""
        
        operations = []
        
        if "energy_critical_deficit" in scenario:
            operations.extend(self._create_critical_charging_operations(
                price_windows, energy_strategy, current_battery_level, battery_capacity_wh, max_power_w
            ))
            
        elif "energy_critical_surplus" in scenario:
            operations.extend(self._create_critical_selling_operations(
                price_windows, energy_strategy, current_battery_level, battery_capacity_wh, max_power_w
            ))
            
        elif "energy_surplus_both_days" in scenario:
            operations.extend(self._create_surplus_selling_operations(
                price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency
            ))
            
        elif "energy_deficit_both_days" in scenario:
            operations.extend(self._create_deficit_charging_operations(
                price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency
            ))
            
        elif "surplus_today_deficit_tomorrow" in scenario:
            operations.extend(self._create_transition_operations(
                price_windows, energy_balances, current_battery_level, battery_capacity_wh, max_power_w, "surplus_to_deficit", currency
            ))
            
        elif "deficit_today_surplus_tomorrow" in scenario:
            operations.extend(self._create_transition_operations(
                price_windows, energy_balances, current_battery_level, battery_capacity_wh, max_power_w, "deficit_to_surplus", currency
            ))
            
        elif "price_driven" in scenario:
            operations.extend(self._create_opportunistic_operations(
                price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency
            ))
            
        # Always add monitoring holds between operations
        operations.extend(self._create_hold_operations(operations, price_windows))
        
        return operations
    
    def _create_critical_charging_operations(self, price_windows, energy_strategy, current_battery_level, battery_capacity_wh, max_power_w) -> List[PlannedOperation]:
        """Create urgent charging operations."""
        operations = []
        
        # Find the best charging windows
        buy_windows = [w for w in price_windows if w.action == 'buy']
        buy_windows.sort(key=lambda w: (w.urgency != 'high', w.price))
        
        target_battery_level = energy_strategy['target_battery_level']
        target_energy = ((target_battery_level - current_battery_level) / 100) * battery_capacity_wh
        
        remaining_energy = max(0, target_energy)
        
        for window in buy_windows[:3]:  # Use up to 3 best windows
            if remaining_energy <= 100:  # Less than 100Wh remaining
                break
                
            # Calculate energy for this window
            window_energy = min(remaining_energy, window.max_energy_capacity(max_power_w))
            window_power = min(max_power_w, window_energy / window.duration_hours)
            
            operation = PlannedOperation(
                operation_type=OperationType.CHARGE_URGENT,
                start_time=window.start_time,
                end_time=window.start_time + timedelta(hours=window_energy / window_power),
                target_energy_wh=window_energy,
                target_power_w=window_power,
                expected_price=window.price,
                confidence=window.confidence,
                priority=1 if window.urgency == 'high' else 2,
                reason=f"Critical charging: {window_energy:.0f}Wh needed for energy deficit",
                dependencies=[],
                alternatives=[]
            )
            
            operations.append(operation)
            remaining_energy -= window_energy
            
        return operations
    
    def _create_critical_selling_operations(self, price_windows, energy_strategy, current_battery_level, battery_capacity_wh, max_power_w) -> List[PlannedOperation]:
        """Create urgent selling operations."""
        operations = []
        
        # Find the best selling windows
        sell_windows = [w for w in price_windows if w.action == 'sell']
        sell_windows.sort(key=lambda w: (w.urgency != 'high', -w.price))  # Highest price first
        
        # Calculate available energy above minimum reserve
        min_reserve = self.sensor_helper.get_min_arbitrage_depth()  # %
        available_energy = ((current_battery_level - min_reserve) / 100) * battery_capacity_wh
        
        remaining_energy = max(0, available_energy)
        
        for window in sell_windows[:3]:  # Use up to 3 best windows
            if remaining_energy <= 100:  # Less than 100Wh remaining
                break
                
            # Calculate energy for this window
            window_energy = min(remaining_energy, window.max_energy_capacity(max_power_w))
            window_power = min(max_power_w, window_energy / window.duration_hours)
            
            operation = PlannedOperation(
                operation_type=OperationType.SELL_URGENT,
                start_time=window.start_time,
                end_time=window.start_time + timedelta(hours=window_energy / window_power),
                target_energy_wh=window_energy,
                target_power_w=window_power,
                expected_price=window.price,
                confidence=window.confidence,
                priority=1 if window.urgency == 'high' else 2,
                reason=f"Critical selling: {window_energy:.0f}Wh excess energy to market",
                dependencies=[],
                alternatives=[]
            )
            
            operations.append(operation)
            remaining_energy -= window_energy
            
        return operations
    
    def _create_surplus_selling_operations(self, price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency: str = "PLN") -> List[PlannedOperation]:
        """Create operations for selling surplus energy."""
        operations = []
        
        sell_windows = [w for w in price_windows if w.action == 'sell']
        sell_windows.sort(key=lambda w: -w.price)  # Highest price first
        
        # Conservative selling - keep some battery for unexpected needs
        min_keep_level = max(50, self.sensor_helper.get_min_arbitrage_depth())  # Keep at least 50%
        available_energy = ((current_battery_level - min_keep_level) / 100) * battery_capacity_wh
        
        if available_energy > 500:  # Only sell if we have significant surplus
            for window in sell_windows[:2]:  # Use top 2 selling opportunities
                window_energy = min(available_energy * 0.6, window.max_energy_capacity(max_power_w))  # Sell up to 60% of surplus
                
                if window_energy > 200:  # Minimum 200Wh to make it worthwhile
                    window_power = min(max_power_w, window_energy / window.duration_hours)
                    
                    operation = PlannedOperation(
                        operation_type=OperationType.SELL_OPTIMAL,
                        start_time=window.start_time,
                        end_time=window.start_time + timedelta(hours=window_energy / window_power),
                        target_energy_wh=window_energy,
                        target_power_w=window_power,
                        expected_price=window.price,
                        confidence=window.confidence * 0.9,  # Slightly lower confidence for optimal operations
                        priority=3,
                        reason=f"Surplus selling: {window_energy:.0f}Wh at good price {currency} {window.price:.3f}",
                        dependencies=[],
                        alternatives=[]
                    )
                    
                    operations.append(operation)
                    available_energy -= window_energy
        
        return operations
    
    def _create_deficit_charging_operations(self, price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency: str = "PLN") -> List[PlannedOperation]:
        """Create operations for charging during deficit periods."""
        operations = []
        
        buy_windows = [w for w in price_windows if w.action == 'buy']
        buy_windows.sort(key=lambda w: w.price)  # Lowest price first
        
        # Target 80% charge to handle deficit
        target_battery_level = 80
        target_energy = ((target_battery_level - current_battery_level) / 100) * battery_capacity_wh
        
        if target_energy > 500:  # Only if we need significant energy
            remaining_energy = target_energy
            
            for window in buy_windows[:2]:  # Use top 2 buying opportunities
                window_energy = min(remaining_energy, window.max_energy_capacity(max_power_w))
                
                if window_energy > 200:  # Minimum 200Wh
                    window_power = min(max_power_w, window_energy / window.duration_hours)
                    
                    operation = PlannedOperation(
                        operation_type=OperationType.CHARGE_OPTIMAL,
                        start_time=window.start_time,
                        end_time=window.start_time + timedelta(hours=window_energy / window_power),
                        target_energy_wh=window_energy,
                        target_power_w=window_power,
                        expected_price=window.price,
                        confidence=window.confidence * 0.9,
                        priority=3,
                        reason=f"Deficit charging: {window_energy:.0f}Wh at low price {currency} {window.price:.3f}",
                        dependencies=[],
                        alternatives=[]
                    )
                    
                    operations.append(operation)
                    remaining_energy -= window_energy
        
        return operations
    
    def _create_transition_operations(self, price_windows, energy_balances, current_battery_level, battery_capacity_wh, max_power_w, transition_type, currency: str = "PLN") -> List[PlannedOperation]:
        """Create operations for transition scenarios."""
        operations = []
        
        if transition_type == "surplus_to_deficit":
            # Sell surplus today, prepare for deficit tomorrow
            # FIXED: Use HA timezone for date comparisons
            ha_now = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
            sell_windows = [w for w in price_windows if w.action == 'sell' and w.start_time.date() == ha_now.date()]
            buy_windows = [w for w in price_windows if w.action == 'buy' and w.start_time.date() > ha_now.date()]
            
            # Moderate selling today
            operations.extend(self._create_surplus_selling_operations(sell_windows + price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency))
            # Strategic buying for tomorrow
            operations.extend(self._create_deficit_charging_operations(buy_windows + price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency))
            
        elif transition_type == "deficit_to_surplus":
            # Charge today, prepare to sell tomorrow  
            # FIXED: Use HA timezone for date comparisons
            ha_now = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
            buy_windows = [w for w in price_windows if w.action == 'buy' and w.start_time.date() == ha_now.date()]
            sell_windows = [w for w in price_windows if w.action == 'sell' and w.start_time.date() > ha_now.date()]
            
            # Strategic charging today
            operations.extend(self._create_deficit_charging_operations(buy_windows + price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency))
            # Prepare selling for tomorrow
            operations.extend(self._create_surplus_selling_operations(sell_windows + price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency))
        
        return operations
    
    def _create_opportunistic_operations(self, price_windows, current_battery_level, battery_capacity_wh, max_power_w, currency: str = "PLN") -> List[PlannedOperation]:
        """Create operations based purely on price opportunities."""
        operations = []
        
        # Sort all windows by potential profit
        all_windows = price_windows.copy()
        
        # Create moderate operations for the best opportunities
        buy_windows = [w for w in all_windows if w.action == 'buy'][:2]
        sell_windows = [w for w in all_windows if w.action == 'sell'][:2]
        
        for window in buy_windows:
            if current_battery_level < 90:  # Only buy if not nearly full
                energy = min(2000, window.max_energy_capacity(max_power_w))  # Up to 2kWh
                power = min(max_power_w, energy / window.duration_hours)
                
                operation = PlannedOperation(
                    operation_type=OperationType.CHARGE_OPTIMAL,
                    start_time=window.start_time,
                    end_time=window.start_time + timedelta(hours=energy / power),
                    target_energy_wh=energy,
                    target_power_w=power,
                    expected_price=window.price,
                    confidence=window.confidence * 0.8,  # Lower confidence for opportunistic
                    priority=4,
                    reason=f"Opportunistic buy: {energy:.0f}Wh at {currency} {window.price:.3f}",
                    dependencies=[],
                    alternatives=[]
                )
                operations.append(operation)
        
        for window in sell_windows:
            if current_battery_level > 30:  # Only sell if not low
                available = ((current_battery_level - 20) / 100) * battery_capacity_wh  # Keep 20% reserve
                energy = min(available * 0.5, window.max_energy_capacity(max_power_w))  # Sell up to 50% of available
                
                if energy > 200:
                    power = min(max_power_w, energy / window.duration_hours)
                    
                    operation = PlannedOperation(
                        operation_type=OperationType.SELL_OPTIMAL,
                        start_time=window.start_time,
                        end_time=window.start_time + timedelta(hours=energy / power),
                        target_energy_wh=energy,
                        target_power_w=power,
                        expected_price=window.price,
                        confidence=window.confidence * 0.8,
                        priority=4,
                        reason=f"Opportunistic sell: {energy:.0f}Wh at {currency} {window.price:.3f}",
                        dependencies=[],
                        alternatives=[]
                    )
                    operations.append(operation)
        
        return operations
    
    def _create_hold_operations(self, existing_operations: List[PlannedOperation], price_windows) -> List[PlannedOperation]:
        """Create hold operations to fill gaps between active operations."""
        if not existing_operations:
            # If no operations planned, create a single monitoring hold
            return [PlannedOperation(
                operation_type=OperationType.HOLD_WAIT,
                # FIXED: Use HA timezone for operation scheduling
                start_time=get_current_ha_time(getattr(self.sensor_helper, 'hass', None)),
                end_time=get_current_ha_time(getattr(self.sensor_helper, 'hass', None)) + timedelta(hours=24),
                target_energy_wh=0,
                target_power_w=0,
                expected_price=0,
                confidence=1.0,
                priority=5,
                reason="Monitoring mode: No beneficial operations identified",
                dependencies=[],
                alternatives=[]
            )]
        
        # For now, don't create explicit hold operations between other operations
        # The optimizer will handle holds automatically
        return []
    
    def _optimize_operation_sequence(self, operations: List[PlannedOperation], current_battery_level: float, battery_capacity_wh: float) -> List[PlannedOperation]:
        """Optimize the sequence of operations for feasibility."""
        if not operations:
            return operations
        
        # Sort operations by start time
        operations.sort(key=lambda op: op.start_time)
        
        # Track battery state through operations
        battery_energy_wh = (current_battery_level / 100) * battery_capacity_wh
        optimized_operations = []
        
        for operation in operations:
            
            # Check if operation is feasible given current battery state
            if operation.operation_type in [OperationType.CHARGE_URGENT, OperationType.CHARGE_OPTIMAL]:
                max_charge_energy = battery_capacity_wh - battery_energy_wh
                
                if max_charge_energy > 100:  # At least 100Wh worth charging
                    actual_energy = min(operation.target_energy_wh, max_charge_energy)
                    
                    # Update operation with actual energy
                    operation.target_energy_wh = actual_energy
                    operation.target_power_w = min(operation.target_power_w, actual_energy / operation.duration_hours)
                    
                    optimized_operations.append(operation)
                    battery_energy_wh += actual_energy
            
            elif operation.operation_type in [OperationType.SELL_URGENT, OperationType.SELL_OPTIMAL]:
                min_reserve_wh = (20 / 100) * battery_capacity_wh  # Keep 20% minimum
                max_discharge_energy = battery_energy_wh - min_reserve_wh
                
                if max_discharge_energy > 100:  # At least 100Wh worth discharging
                    actual_energy = min(operation.target_energy_wh, max_discharge_energy)
                    
                    # Update operation with actual energy
                    operation.target_energy_wh = actual_energy
                    operation.target_power_w = min(operation.target_power_w, actual_energy / operation.duration_hours)
                    
                    optimized_operations.append(operation)
                    battery_energy_wh -= actual_energy
            
            else:  # Hold operations
                optimized_operations.append(operation)
        
        return optimized_operations
    
    def _calculate_plan_profit(self, operations: List[PlannedOperation]) -> float:
        """Calculate expected profit from the plan."""
        total_profit = 0.0
        
        # Simplified profit calculation based on operation types and prices
        for operation in operations:
            energy_kwh = operation.target_energy_wh / 1000
            
            if operation.operation_type in [OperationType.CHARGE_URGENT, OperationType.CHARGE_OPTIMAL]:
                # Cost of buying energy (negative profit)
                total_profit -= energy_kwh * operation.expected_price
            elif operation.operation_type in [OperationType.SELL_URGENT, OperationType.SELL_OPTIMAL]:
                # Income from selling energy (positive profit)
                total_profit += energy_kwh * operation.expected_price * 0.9  # Account for losses
        
        return total_profit
    
    def _assess_plan_risk(self, operations: List[PlannedOperation], energy_balances) -> str:
        """Assess the risk level of the plan."""
        
        # High risk factors
        urgent_operations = [op for op in operations if op.priority <= 2]
        low_confidence_operations = [op for op in operations if op.confidence < 0.6]
        
        if len(urgent_operations) > 2:
            return "high"  # Too many urgent operations
        
        if len(low_confidence_operations) > len(operations) * 0.5:
            return "high"  # Too many low-confidence operations
        
        # Medium risk factors
        if len(urgent_operations) > 0 or len(low_confidence_operations) > 0:
            return "medium"
        
        # Low risk
        return "low"
    
    def _create_fallback_plan(self, main_plan: StrategicPlan, current_battery_level: float, battery_capacity_wh: float, max_power_w: float) -> StrategicPlan:
        """Create a conservative fallback plan."""
        
        # Simple conservative operations
        operations = []
        
        # If battery is low, add conservative charging
        if current_battery_level < 40:
            operations.append(PlannedOperation(
                operation_type=OperationType.CHARGE_URGENT,
                # FIXED: Use HA timezone for critical charge operation
                start_time=get_current_ha_time(getattr(self.sensor_helper, 'hass', None)),
                end_time=get_current_ha_time(getattr(self.sensor_helper, 'hass', None)) + timedelta(hours=4),
                target_energy_wh=2000,  # 2kWh
                target_power_w=500,     # 500W
                expected_price=0.2,     # Conservative price
                confidence=0.8,
                priority=1,
                reason="Fallback: Conservative charging to ensure minimum energy",
                dependencies=[],
                alternatives=[]
            ))
        
        # Add monitoring hold
        # FIXED: Use HA timezone for conservative operation scheduling
        ha_now = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
        operations.append(PlannedOperation(
            operation_type=OperationType.HOLD_PRESERVE,
            start_time=ha_now + timedelta(hours=4),
            end_time=ha_now + timedelta(hours=24),
            target_energy_wh=0,
            target_power_w=0,
            expected_price=0,
            confidence=1.0,
            priority=5,
            reason="Fallback: Preserve energy until conditions improve",
            dependencies=[],
            alternatives=[]
        ))
        
        return StrategicPlan(
            plan_id=f"fallback_{main_plan.plan_id}",
            # FIXED: Use HA timezone for fallback plan creation timestamp
            created_at=get_current_ha_time(getattr(self.sensor_helper, 'hass', None)),
            valid_until=main_plan.valid_until,
            operations=operations,
            expected_profit=-0.4,  # Conservative cost estimate
            risk_assessment="low",
            scenario="fallback_conservative",
            confidence=0.9,
            fallback_plan=None
        )
    
    def _create_emergency_plan(self, current_battery_level: float, battery_capacity_wh: float) -> StrategicPlan:
        """Create an emergency plan when main planning fails."""
        
        # FIXED: Use HA timezone for emergency operation scheduling
        ha_now = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
        operation = PlannedOperation(
            operation_type=OperationType.HOLD_PRESERVE,
            start_time=ha_now,
            end_time=ha_now + timedelta(hours=24),
            target_energy_wh=0,
            target_power_w=0,
            expected_price=0,
            confidence=1.0,
            priority=5,
            reason="Emergency mode: System planning failed, holding position",
            dependencies=[],
            alternatives=[]
        )
        
        # FIXED: Use HA timezone for emergency plan timestamps
        ha_now = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
        return StrategicPlan(
            plan_id=f"emergency_{ha_now.strftime('%Y%m%d_%H%M%S')}",
            created_at=ha_now,
            valid_until=ha_now + timedelta(hours=24),
            operations=[operation],
            expected_profit=0,
            risk_assessment="low",
            scenario="emergency_hold",
            confidence=1.0,
            fallback_plan=None
        )
    
    def get_current_plan(self) -> Optional[StrategicPlan]:
        """Get the currently active strategic plan."""
        current_time = get_current_ha_time(getattr(self.sensor_helper, 'hass', None))
        
        if not self._current_plan:
            _LOGGER.debug("Strategic Plan: No plan exists (_current_plan is None)")
            return None
            
        if self._current_plan.valid_until <= current_time:
            _LOGGER.info(f"Strategic Plan: Plan expired. Valid until {self._current_plan.valid_until}, current time {current_time}")
            return None
            
        _LOGGER.debug(f"Strategic Plan: Active plan found. Valid until {self._current_plan.valid_until}, current time {current_time}")
        return self._current_plan
    
    def get_current_recommendation(self) -> Dict[str, Any]:
        """Get current recommendation based on active plan."""
        plan = self.get_current_plan()
        
        if not plan:
            return {
                "action": "hold",
                "reason": "No active strategic plan",
                "confidence": 0.5,
                "plan_status": "no_plan"
            }
        
        # Check for active operations
        active_ops = plan.active_operations
        if active_ops:
            op = active_ops[0]  # Take the first active operation
            
            if op.operation_type in [OperationType.CHARGE_URGENT, OperationType.CHARGE_OPTIMAL]:
                return {
                    "action": "charge_arbitrage",
                    "reason": f"🎯 STRATEGIC: {op.reason}",
                    "target_power": op.target_power_w,
                    "confidence": op.confidence,
                    "plan_status": "executing",
                    "operation_id": op.operation_id,
                    "priority": op.priority
                }
            elif op.operation_type in [OperationType.SELL_URGENT, OperationType.SELL_OPTIMAL]:
                return {
                    "action": "sell_arbitrage",
                    "reason": f"🎯 STRATEGIC: {op.reason}",
                    "target_power": -op.target_power_w,
                    "confidence": op.confidence,
                    "plan_status": "executing",
                    "operation_id": op.operation_id,
                    "priority": op.priority
                }
        
        # Check for upcoming operations
        upcoming = plan.upcoming_operations
        if upcoming:
            next_op = upcoming[0]
            # FIXED: Use HA timezone for time calculations
            time_until = (next_op.start_time - get_current_ha_time(getattr(self.sensor_helper, 'hass', None))).total_seconds() / 60
            
            return {
                "action": "hold",
                "reason": f"🎯 STRATEGIC: Preparing for {next_op.operation_type.value} in {time_until:.0f}min",
                "confidence": plan.confidence,
                "plan_status": "waiting",
                "next_operation": next_op.operation_id,
                "time_until_next": time_until
            }
        
        # Plan exists but no immediate actions
        next_op = plan.next_operation
        if next_op:
            # FIXED: Use HA timezone for time calculations
            time_until = (next_op.start_time - get_current_ha_time(getattr(self.sensor_helper, 'hass', None))).total_seconds() / 3600
            return {
                "action": "hold",
                "reason": f"🎯 STRATEGIC: Next operation in {time_until:.1f}h ({next_op.operation_type.value})",
                "confidence": plan.confidence,
                "plan_status": "monitoring",
                "next_operation": next_op.operation_id,
                "time_until_next": time_until
            }
        
        # Plan completed
        return {
            "action": "hold",
            "reason": "🎯 STRATEGIC: Plan completed, monitoring for new opportunities",
            "confidence": plan.confidence,
            "plan_status": "completed"
        }
