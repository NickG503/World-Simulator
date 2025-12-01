"""
Simulation Runner: Execute multiple actions sequentially and track state history.

Simplified for tree-based simulation:
- No interactive questioning/clarification
- Linear execution through actions
- State tracking via snapshots

This module will be replaced by TreeSimulationRunner for tree-based execution.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import yaml
from pydantic import BaseModel, Field

from simulator.core.engine.transition_engine import DiffEntry, TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager


class AttributeSnapshot(BaseModel):
    """
    Snapshot of an attribute's state.

    In Phase 2, the value can be either:
    - A single string value (known state)
    - A list of strings (set of possible values from branching/trends)
    - None (uninitialized)
    """

    value: Union[str, List[str], None] = None  # Single value OR set of possible values
    trend: Optional[str] = None
    last_known_value: Optional[str] = None
    last_trend_direction: Optional[str] = None
    space_id: Optional[str] = None

    def is_value_set(self) -> bool:
        """Check if the value is a set of possible values (list)."""
        return isinstance(self.value, list)

    def get_value_as_set(self) -> Set[str]:
        """
        Get the value as a set.

        Returns:
            Set of possible values. For single values, returns a set with one element.
            For value sets, returns the set of all values.
            For None, returns empty set.
        """
        if isinstance(self.value, list):
            return set(self.value)
        return {self.value} if self.value else set()

    def get_single_value(self) -> Optional[str]:
        """
        Get the value as a single string.

        Returns:
            The single value, or the first value if a set, or None.
        """
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def is_unknown(self) -> bool:
        """
        Check if the attribute value is unknown.

        In Phase 2, a value is "unknown" if:
        - It's None
        - It's the string "unknown"
        - It's a set with more than one value (uncertain state)
        """
        if self.value is None:
            return True
        if isinstance(self.value, list):
            return len(self.value) != 1
        return self.value == "unknown"


class PartStateSnapshot(BaseModel):
    attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ObjectStateSnapshot(BaseModel):
    type: str
    parts: Dict[str, PartStateSnapshot] = Field(default_factory=dict)
    global_attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    name: str
    parameters: Dict[str, str] = Field(default_factory=dict)


class SimulationStep(BaseModel):
    """Represents a single step in the simulation."""

    step_number: int
    action_name: str
    object_name: str
    parameters: Dict[str, str] = Field(default_factory=dict)
    status: str  # "ok", "rejected", "error"
    error_message: Optional[str] = None
    object_state_before: Optional[ObjectStateSnapshot] = None
    object_state_after: Optional[ObjectStateSnapshot] = None
    changes: List[DiffEntry] = Field(default_factory=list)


class SimulationHistory(BaseModel):
    """Complete history of a simulation run."""

    simulation_id: str
    object_type: str
    object_name: str
    started_at: str
    total_steps: int = 0
    steps: List[SimulationStep] = Field(default_factory=list)
    initial_state: Optional[ObjectStateSnapshot] = None

    def get_state_at_step(self, step_number: int) -> Optional[ObjectStateSnapshot]:
        """Get object state after a specific step (0-based)."""
        if step_number < 0 or step_number >= len(self.steps):
            return None
        self.ensure_state_cache()
        return self.steps[step_number].object_state_after

    def get_initial_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the initial object state (before any actions)."""
        if self.initial_state is not None:
            return self.initial_state
        if not self.steps:
            return None
        return self.steps[0].object_state_before

    def get_final_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the final object state (after all actions)."""
        if not self.steps:
            return None
        self.ensure_state_cache()
        return self.steps[-1].object_state_after

    def get_successful_steps(self) -> List[SimulationStep]:
        """Get all steps that completed successfully."""
        return [step for step in self.steps if step.status == "ok"]

    def get_failed_steps(self) -> List[SimulationStep]:
        """Get all steps that failed."""
        return [step for step in self.steps if step.status != "ok"]

    def ensure_state_cache(self) -> None:
        """Ensure before/after snapshots are populated using initial_state and deltas."""
        if not self.steps:
            return
        base_state = self.initial_state
        if base_state is None and self.steps[0].object_state_before is not None:
            base_state = self.steps[0].object_state_before.model_copy(deep=True)
        if base_state is None:
            return

        cursor = base_state.model_copy(deep=True)
        for step in self.steps:
            if step.object_state_before is None:
                step.object_state_before = cursor.model_copy(deep=True)
            cursor = _apply_changes_to_snapshot(cursor, step.changes)
            step.object_state_after = cursor.model_copy(deep=True)


def _ensure_attr_snapshot(state: ObjectStateSnapshot, part: Optional[str], attr: str) -> AttributeSnapshot:
    """Ensure an AttributeSnapshot exists for the given path on a state snapshot."""
    if part:
        if part not in state.parts:
            state.parts[part] = PartStateSnapshot()
        part_state = state.parts[part]
        if attr not in part_state.attributes:
            part_state.attributes[attr] = AttributeSnapshot(value=None, trend=None)
        return part_state.attributes[attr]

    if attr not in state.global_attributes:
        state.global_attributes[attr] = AttributeSnapshot(value=None, trend=None)
    return state.global_attributes[attr]


def _apply_changes_to_snapshot(state: ObjectStateSnapshot, changes: List[DiffEntry]) -> ObjectStateSnapshot:
    """Produce a new snapshot by applying a list of DiffEntry changes."""
    new_state = state.model_copy(deep=True)
    for change in changes:
        attr_path = change.attribute or ""
        parts = attr_path.split(".")
        is_trend = change.kind == "trend" or (parts and parts[-1] == "trend")
        if is_trend and parts:
            parts = parts[:-1]

        part_name: Optional[str] = None
        attr_name: Optional[str] = None

        if not parts:
            continue
        if len(parts) == 1:
            attr_name = parts[0]
        else:
            part_name = parts[0]
            attr_name = parts[1]

        if attr_name is None:
            continue

        attr_snapshot = _ensure_attr_snapshot(new_state, part_name, attr_name)
        if is_trend:
            # Set trend direction but keep the current value as-is (no unknowns)
            if change.after in ("up", "down"):
                attr_snapshot.last_trend_direction = change.after
            else:
                attr_snapshot.last_trend_direction = None
            attr_snapshot.trend = change.after
        else:
            # Update the value directly
            attr_snapshot.last_known_value = change.after
            attr_snapshot.value = change.after
    return new_state


class SimulationRunner:
    """Runs multiple actions in sequence and tracks state history."""

    def __init__(self, registry_manager: RegistryManager):
        self.registry_manager = registry_manager
        self.engine = TransitionEngine(registry_manager)

    def run_simulation(
        self,
        object_type: str,
        actions: List[Union[ActionRequest, Dict[str, str], Dict[str, Dict[str, str]]]],
        simulation_id: Optional[str] = None,
        verbose: bool = False,
    ) -> SimulationHistory:
        """
        Run a simulation with multiple actions.

        Args:
            object_type: Type of object to simulate
            actions: List of actions to execute
            simulation_id: Optional ID for the simulation
            verbose: Whether to log progress

        Returns:
            SimulationHistory with complete timeline
        """
        if not simulation_id:
            simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create object instance
        obj_type = self.registry_manager.objects.get(object_type)
        from simulator.io.loaders.object_loader import instantiate_default

        obj_instance = instantiate_default(obj_type, self.registry_manager)

        # Initialize simulation history
        history = SimulationHistory(
            simulation_id=simulation_id,
            object_type=object_type,
            object_name=object_type,
            started_at=datetime.now().date().isoformat(),
            total_steps=len(actions),
        )

        logger = logging.getLogger(__name__)

        current_instance = obj_instance
        action_requests = [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action) for action in actions
        ]

        for step_num, request in enumerate(action_requests):
            action_name = request.name
            parameters = request.parameters

            # Capture state before action
            state_before = self._capture_object_state(current_instance)
            if history.initial_state is None:
                history.initial_state = state_before.model_copy(deep=True)

            # Get and execute action
            action = self.registry_manager.create_behavior_enhanced_action(object_type, action_name)

            if not action:
                step = SimulationStep(
                    step_number=step_num,
                    action_name=action_name,
                    object_name=object_type,
                    parameters=parameters,
                    status="error",
                    error_message=f"Action '{action_name}' not found for {object_type}",
                    object_state_before=state_before,
                    object_state_after=state_before,
                    changes=[],
                )
                history.steps.append(step)
                if verbose:
                    logger.warning("Action '%s' not found for object '%s'", action_name, object_type)
                continue

            # Execute action
            result = self.engine.apply_action(current_instance, action, parameters)

            # Capture state after action
            state_after = self._capture_object_state(result.after if result.after else current_instance)

            # Create simulation step
            step = SimulationStep(
                step_number=step_num,
                action_name=action_name,
                object_name=object_type,
                parameters=parameters,
                status=result.status,
                error_message=result.reason if result.status != "ok" else None,
                object_state_before=state_before,
                object_state_after=state_after,
                changes=result.changes,
            )

            history.steps.append(step)

            # Update current instance for next iteration
            if result.after:
                current_instance = result.after

            if verbose:
                if result.status == "ok":
                    logger.info("✅ %s ran successfully", action_name)
                else:
                    logger.warning("Action failed: %s", result.reason)

        return history

    def _capture_object_state(self, obj_instance: ObjectInstance) -> ObjectStateSnapshot:
        """Capture the complete state of an object instance."""

        parts: Dict[str, PartStateSnapshot] = {}
        for part_name, part_instance in obj_instance.parts.items():
            attrs: Dict[str, AttributeSnapshot] = {}
            for attr_name, attr_instance in part_instance.attributes.items():
                attrs[attr_name] = AttributeSnapshot(
                    value=attr_instance.current_value,
                    trend=attr_instance.trend,
                    last_known_value=attr_instance.last_known_value,
                    last_trend_direction=attr_instance.last_trend_direction,
                    space_id=attr_instance.spec.space_id,
                )
            parts[part_name] = PartStateSnapshot(attributes=attrs)

        global_attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in obj_instance.global_attributes.items():
            global_attrs[attr_name] = AttributeSnapshot(
                value=attr_instance.current_value,
                trend=attr_instance.trend,
                last_known_value=attr_instance.last_known_value,
                last_trend_direction=attr_instance.last_trend_direction,
                space_id=attr_instance.spec.space_id,
            )

        return ObjectStateSnapshot(
            type=obj_instance.type.name,
            parts=parts,
            global_attributes=global_attrs,
        )

    def save_history_to_yaml(self, history: SimulationHistory, file_path: str) -> None:
        """Save simulation history to YAML file."""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "history_version": 3,
            "simulation_id": history.simulation_id,
            "object_name": history.object_name,
            "started_at": history.started_at,
            "total_steps": history.total_steps,
            "steps": [],
        }
        history.ensure_state_cache()
        if history.initial_state is None and history.steps and history.steps[0].object_state_before is not None:
            history.initial_state = history.steps[0].object_state_before.model_copy(deep=True)
        if history.initial_state is not None:
            data["initial_state"] = history.initial_state.model_dump()

        for s in history.steps:
            step_entry: Dict[str, Any] = {
                "step": s.step_number,
                "action": s.action_name,
                "status": s.status,
            }
            if s.error_message:
                step_entry["error"] = s.error_message
            if s.changes:
                filtered_changes = [c for c in s.changes if c.kind != "info" and not c.attribute.startswith("[")]
                if filtered_changes:
                    step_entry["changes"] = [
                        {"attribute": c.attribute, "before": c.before, "after": c.after, "kind": c.kind}
                        for c in filtered_changes
                    ]
            data["steps"].append(step_entry)

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)

    def load_history_from_yaml(self, file_path: str) -> SimulationHistory:
        """Load simulation history from YAML file."""
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict) and data.get("history_version") == 3 and "steps" in data:
            sim_id = data.get("simulation_id", "unknown")
            obj_name = data.get("object_name") or data.get("object_type", "unknown")
            obj_type = data.get("object_type", obj_name)
            started = data.get("started_at")
            total = data.get("total_steps", len(data.get("steps") or []))

            initial_state_raw = data.get("initial_state")
            initial_state: Optional[ObjectStateSnapshot] = None
            if initial_state_raw:
                try:
                    initial_state = ObjectStateSnapshot.model_validate(initial_state_raw)
                except Exception as exc:
                    raise ValueError(f"Invalid initial_state in history file: {exc}") from exc

            steps: List[SimulationStep] = []
            cursor = initial_state.model_copy(deep=True) if initial_state is not None else None

            for entry in data.get("steps", []):
                step_num = entry.get("step") if entry.get("step") is not None else entry.get("step_number", 0)
                action = entry.get("action") or entry.get("action_name")
                status = entry.get("status", "ok")
                error = entry.get("error") or entry.get("error_message")

                changes_raw = entry.get("changes", []) or []
                changes: List[DiffEntry] = []
                for cr in changes_raw:
                    try:
                        changes.append(DiffEntry(**cr))
                    except Exception:
                        continue

                before_snapshot: Optional[ObjectStateSnapshot] = (
                    cursor.model_copy(deep=True) if cursor is not None else None
                )
                after_snapshot: Optional[ObjectStateSnapshot] = None
                if cursor is not None:
                    after_snapshot = _apply_changes_to_snapshot(cursor, changes)
                    cursor = after_snapshot.model_copy(deep=True)

                steps.append(
                    SimulationStep(
                        step_number=int(step_num),
                        action_name=str(action),
                        object_name=str(obj_name),
                        parameters={},
                        status=str(status),
                        error_message=error,
                        object_state_before=before_snapshot,
                        object_state_after=after_snapshot,
                        changes=changes,
                    )
                )

            history = SimulationHistory(
                simulation_id=str(sim_id),
                object_type=str(obj_type),
                object_name=str(obj_name),
                started_at=str(started),
                total_steps=int(total),
                steps=steps,
                initial_state=initial_state,
            )
            history.ensure_state_cache()
            return history

        # Fallback to legacy format
        return SimulationHistory.model_validate(data)


def create_simulation_runner(registry_manager: RegistryManager) -> SimulationRunner:
    """Factory function to create a simulation runner."""
    return SimulationRunner(registry_manager)
