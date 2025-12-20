"""Constraint enforcement for tree simulation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, List, Optional, Tuple

from simulator.core.attributes import AttributePath
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.tree.models import WorldSnapshot
from simulator.core.types import ChangeDict


def enforce_constraints(
    snapshot: WorldSnapshot,
    object_type_name: str,
    registry_manager: RegistryManager,
) -> Tuple[WorldSnapshot, List[ChangeDict]]:
    """Enforce constraints on snapshot, returning modified snapshot and changes."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.constraints.constraint import DependencyConstraint

    obj_type = registry_manager.objects.get(object_type_name)
    if not obj_type or not obj_type.compiled_constraints:
        return snapshot, []

    changes: List[ChangeDict] = []
    modified = deepcopy(snapshot)

    for constraint in obj_type.compiled_constraints:
        if not isinstance(constraint, DependencyConstraint):
            continue

        # Check if condition is an attribute check
        condition = constraint.condition
        requires = constraint.requires

        if not isinstance(condition, AttributeCondition):
            continue
        if not isinstance(requires, AttributeCondition):
            continue

        # Get current values from snapshot
        condition_target = condition.target.to_string()
        requires_target = requires.target.to_string()

        condition_value = get_snapshot_value(modified, condition_target)
        requires_value = get_snapshot_value(modified, requires_target)

        # Evaluate condition (e.g., bulb.state == on)
        condition_met = _evaluate_condition(condition, condition_value)
        if not condition_met:
            continue  # Constraint satisfied trivially

        # Evaluate requires (e.g., battery.level != empty)
        requires_met = _evaluate_condition(requires, requires_value)
        if requires_met:
            continue  # Constraint satisfied

        # Constraint violated! Fix by making condition false
        if condition.operator == "equals":
            # Get opposite value from the space
            opposite_value = _get_opposite_value(condition_target, condition.value, modified, registry_manager)
            if opposite_value:
                old_value = condition_value
                set_snapshot_value(modified, condition_target, opposite_value)
                changes.append(
                    {
                        "attribute": condition_target,
                        "before": old_value,
                        "after": opposite_value,
                        "kind": "constraint",
                    }
                )

                # Handle related attributes
                related_changes = _apply_related_effects(modified, condition_target, opposite_value)
                changes.extend(related_changes)

    return modified, changes


def get_snapshot_value(snapshot: WorldSnapshot, attr_path: str) -> Any:
    """Get attribute value from snapshot."""
    return AttributePath.parse(attr_path).get_value_from_snapshot(snapshot)


def set_snapshot_value(snapshot: WorldSnapshot, attr_path: str, value: Any) -> None:
    """Set attribute value in snapshot."""
    AttributePath.parse(attr_path).set_value_in_snapshot(snapshot, value)


def get_snapshot_attr(snapshot: WorldSnapshot, attr_path: str):
    """Get attribute object from snapshot (for accessing space_id, trend, etc.)."""
    return AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)


def _evaluate_condition(condition, value: Any) -> bool:
    """Evaluate a simple attribute condition against a value."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

    if not isinstance(condition, AttributeCondition):
        return False

    expected = condition.value
    op = condition.operator

    # Handle value sets
    if isinstance(value, list):
        if op == "equals":
            return expected in value
        elif op == "not_equals":
            return expected not in value or len(value) > 1
    else:
        if op == "equals":
            return value == expected
        elif op == "not_equals":
            return value != expected

    return False


def _get_opposite_value(
    attr_path: str,
    current_value: str,
    snapshot: WorldSnapshot,
    registry_manager: RegistryManager,
) -> Optional[str]:
    """Get the opposite value for an attribute from its space."""
    attr = get_snapshot_attr(snapshot, attr_path)
    if not attr or not attr.space_id:
        return None

    space = registry_manager.spaces.get(attr.space_id)
    if not space or not space.levels:
        return None

    # Get first value that's not the current value
    for v in space.levels:
        if v != current_value:
            return v
    return None


def _apply_related_effects(snapshot: WorldSnapshot, attr_path: str, new_value: str) -> List[ChangeDict]:
    """Apply related effects when an attribute changes due to constraint enforcement."""
    changes: List[ChangeDict] = []

    # When bulb turns off, brightness becomes none
    if attr_path == "bulb.state" and new_value == "off":
        brightness_part = snapshot.object_state.parts.get("bulb")
        if brightness_part:
            brightness = brightness_part.attributes.get("brightness")
            if brightness and brightness.value != "none":
                old_value = brightness.value
                brightness.value = "none"
                changes.append(
                    {
                        "attribute": "bulb.brightness",
                        "before": old_value,
                        "after": "none",
                        "kind": "constraint",
                    }
                )

            # Also clear the trend on battery since flashlight is now off
            battery_part = snapshot.object_state.parts.get("battery")
            if battery_part:
                level_attr = battery_part.attributes.get("level")
                if level_attr and level_attr.trend != "none":
                    level_attr.trend = "none"

    return changes
