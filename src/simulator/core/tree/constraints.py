"""
Constraint enforcement for tree simulation.

This module handles enforcing object constraints during simulation,
particularly when branching creates states that may violate constraints.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.tree.models import WorldSnapshot


def enforce_constraints(
    snapshot: WorldSnapshot,
    object_type_name: str,
    registry_manager: RegistryManager,
) -> Tuple[WorldSnapshot, List[Dict[str, Any]]]:
    """
    Enforce all constraints on a snapshot, modifying it if needed.

    For DependencyConstraints: if condition is true but requires is false,
    modify the snapshot to make condition false.

    Args:
        snapshot: The world snapshot to check and modify
        object_type_name: Name of the object type (to get constraints)
        registry_manager: Registry manager for accessing object types and spaces

    Returns:
        Tuple of (modified_snapshot, list of changes made)
    """
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.constraints.constraint import DependencyConstraint

    obj_type = registry_manager.objects.get(object_type_name)
    if not obj_type or not obj_type.compiled_constraints:
        return snapshot, []

    changes: List[Dict[str, Any]] = []
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
    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in snapshot.object_state.parts:
            attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
            if attr:
                return attr.value
    elif len(parts) == 1:
        attr = snapshot.object_state.global_attributes.get(parts[0])
        if attr:
            return attr.value
    return None


def set_snapshot_value(snapshot: WorldSnapshot, attr_path: str, value: Any) -> None:
    """Set attribute value in snapshot."""
    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in snapshot.object_state.parts:
            attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
            if attr:
                attr.value = value
    elif len(parts) == 1:
        attr = snapshot.object_state.global_attributes.get(parts[0])
        if attr:
            attr.value = value


def get_snapshot_attr(snapshot: WorldSnapshot, attr_path: str):
    """Get attribute object from snapshot (for accessing space_id, trend, etc.)."""
    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in snapshot.object_state.parts:
            return snapshot.object_state.parts[part_name].attributes.get(attr_name)
    elif len(parts) == 1:
        return snapshot.object_state.global_attributes.get(parts[0])
    return None


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


def _apply_related_effects(snapshot: WorldSnapshot, attr_path: str, new_value: str) -> List[Dict[str, Any]]:
    """
    Apply related effects when an attribute changes due to constraint enforcement.

    This handles implicit relationships not captured in explicit constraints.
    For example: when bulb.state='off', brightness should be 'none'.

    Note: This could be made more generic by defining these relationships in YAML.
    For now, we handle known cases explicitly.
    """
    changes: List[Dict[str, Any]] = []

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
