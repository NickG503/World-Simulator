"""
Simulation data models and snapshot utilities.

This module provides the data models used by TreeSimulationRunner:
- AttributeSnapshot: State of a single attribute
- PartStateSnapshot: State of an object part
- ObjectStateSnapshot: Complete object state
- ActionRequest: Action specification
- SimulationStep/SimulationHistory: For loading legacy history files
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field

from simulator.core.engine.transition_engine import DiffEntry


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
