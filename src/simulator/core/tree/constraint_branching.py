"""Branching constraint processor for tree simulation.

This module handles branching constraints that create separate branches
based on atomic state conditions. Unlike regular constraints that silently
fix invalid states, branching constraints create explicit branches in the tree.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from simulator.core.attributes import AttributePath
from simulator.core.constraints.constraint import BranchingConstraint
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.tree.models import WorldSnapshot
from simulator.core.types import ChangeDict


@dataclass
class ConstraintBranchInfo:
    """Information about a constraint branch."""

    constraint_name: Optional[str]
    branch_type: str  # "if" or "else"
    condition_attribute: str
    condition_values: List[str]  # Values that triggered this branch
    has_active_trends: bool  # Whether any attribute has an active trend
    changes: List[ChangeDict]  # Changes made by the constraint


def get_branching_constraints(
    object_type_name: str,
    registry_manager: RegistryManager,
) -> List[BranchingConstraint]:
    """Get all branching constraints for an object type."""
    obj_type = registry_manager.objects.get(object_type_name)
    if not obj_type or not obj_type.compiled_constraints:
        return []

    return [c for c in obj_type.compiled_constraints if isinstance(c, BranchingConstraint)]


def apply_branching_constraints(
    snapshot: WorldSnapshot,
    object_type_name: str,
    registry_manager: RegistryManager,
) -> List[Tuple[WorldSnapshot, ConstraintBranchInfo]]:
    """Apply branching constraints to a snapshot, returning list of (snapshot, branch_info) tuples.

    For each branching constraint:
    - If the condition attribute is a single value: apply effects if condition matches
    - If the condition attribute is a value set: create IF and ELSE branches

    Args:
        snapshot: The current world snapshot
        object_type_name: Name of the object type
        registry_manager: Registry manager for accessing spaces

    Returns:
        List of (modified_snapshot, branch_info) tuples for each branch
    """
    constraints = get_branching_constraints(object_type_name, registry_manager)
    if not constraints:
        # No branching constraints - return snapshot with trend cleanup
        cleaned = cleanup_single_value_trends(snapshot, registry_manager)
        has_trends = _has_active_trends(cleaned)
        return [
            (
                cleaned,
                ConstraintBranchInfo(
                    constraint_name=None,
                    branch_type="none",
                    condition_attribute="",
                    condition_values=[],
                    has_active_trends=has_trends,
                    changes=[],
                ),
            )
        ]

    # Process each constraint (currently supporting one at a time)
    # TODO: Support multiple branching constraints with combinatorial branching
    for constraint in constraints:
        return _apply_single_branching_constraint(snapshot, constraint, registry_manager)

    return [(snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]


def _apply_single_branching_constraint(
    snapshot: WorldSnapshot,
    constraint: BranchingConstraint,
    registry_manager: RegistryManager,
) -> List[Tuple[WorldSnapshot, ConstraintBranchInfo]]:
    """Apply a single branching constraint."""
    attr_path = constraint.get_condition_attribute()
    if not attr_path:
        return [(snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]

    condition_value = constraint.get_condition_value()
    condition_operator = constraint.get_condition_operator()

    # Get current value from snapshot
    current_value = snapshot.get_attribute_value(attr_path)

    # Check if it's a value set (multiple possible values)
    if isinstance(current_value, list):
        # Value set - need to branch
        return _create_constraint_branches(
            snapshot, constraint, attr_path, current_value, condition_value, condition_operator, registry_manager
        )
    else:
        # Single value - check if condition matches
        matches = _value_matches_condition(current_value, condition_value, condition_operator)

        if matches:
            # Apply effects
            modified, changes = _apply_constraint_effects(snapshot, constraint, registry_manager)
            cleaned = cleanup_single_value_trends(modified, registry_manager)
            has_trends = _has_active_trends(cleaned)
            return [
                (
                    cleaned,
                    ConstraintBranchInfo(
                        constraint_name=constraint.name,
                        branch_type="if",
                        condition_attribute=attr_path,
                        condition_values=[current_value] if current_value else [],
                        has_active_trends=has_trends,
                        changes=changes,
                    ),
                )
            ]
        else:
            # Condition doesn't match - return as ELSE branch
            cleaned = cleanup_single_value_trends(snapshot, registry_manager)
            has_trends = _has_active_trends(cleaned)
            return [
                (
                    cleaned,
                    ConstraintBranchInfo(
                        constraint_name=constraint.name,
                        branch_type="else",
                        condition_attribute=attr_path,
                        condition_values=[current_value] if current_value else [],
                        has_active_trends=has_trends,
                        changes=[],
                    ),
                )
            ]


def _create_constraint_branches(
    snapshot: WorldSnapshot,
    constraint: BranchingConstraint,
    attr_path: str,
    current_values: List[str],
    condition_value: Any,
    condition_operator: Optional[str],
    registry_manager: RegistryManager,
) -> List[Tuple[WorldSnapshot, ConstraintBranchInfo]]:
    """Create IF and ELSE branches for a value set."""
    branches: List[Tuple[WorldSnapshot, ConstraintBranchInfo]] = []

    # Split values into matching (IF) and non-matching (ELSE)
    if_values = []
    else_values = []

    for val in current_values:
        if _value_matches_condition(val, condition_value, condition_operator):
            if_values.append(val)
        else:
            else_values.append(val)

    # Create IF branch (condition matches)
    if if_values:
        if_snapshot = deepcopy(snapshot)
        _set_snapshot_value(if_snapshot, attr_path, if_values)
        if_modified, if_changes = _apply_constraint_effects(if_snapshot, constraint, registry_manager)
        if_cleaned = cleanup_single_value_trends(if_modified, registry_manager)
        has_trends = _has_active_trends(if_cleaned)
        branches.append(
            (
                if_cleaned,
                ConstraintBranchInfo(
                    constraint_name=constraint.name,
                    branch_type="if",
                    condition_attribute=attr_path,
                    condition_values=if_values,
                    has_active_trends=has_trends,
                    changes=if_changes,
                ),
            )
        )

    # Create ELSE branch (condition doesn't match)
    if else_values:
        else_snapshot = deepcopy(snapshot)
        _set_snapshot_value(else_snapshot, attr_path, else_values)
        # Apply else_effects to the ELSE branch
        else_modified, else_changes = _apply_constraint_else_effects(else_snapshot, constraint, registry_manager)
        else_cleaned = cleanup_single_value_trends(else_modified, registry_manager)
        has_trends = _has_active_trends(else_cleaned)
        branches.append(
            (
                else_cleaned,
                ConstraintBranchInfo(
                    constraint_name=constraint.name,
                    branch_type="else",
                    condition_attribute=attr_path,
                    condition_values=else_values,
                    has_active_trends=has_trends,
                    changes=else_changes,
                ),
            )
        )

    return branches if branches else [(snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]


def _value_matches_condition(value: Any, condition_value: Any, operator: Optional[str]) -> bool:
    """Check if a value matches a condition."""
    if operator == "equals":
        return value == condition_value
    elif operator == "not_equals":
        return value != condition_value
    elif operator == "in":
        if isinstance(condition_value, list):
            return value in condition_value
        return value == condition_value
    elif operator == "not_in":
        if isinstance(condition_value, list):
            return value not in condition_value
        return value != condition_value
    return False


def _apply_constraint_effects(
    snapshot: WorldSnapshot,
    constraint: BranchingConstraint,
    registry_manager: RegistryManager,
) -> Tuple[WorldSnapshot, List[ChangeDict]]:
    """Apply constraint effects to a snapshot."""
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect

    modified = deepcopy(snapshot)
    changes: List[ChangeDict] = []

    for effect in constraint.effects:
        if isinstance(effect, SetAttributeEffect):
            attr_path = effect.target.to_string()
            new_value = effect.value

            # Get old value
            old_value = modified.get_attribute_value(attr_path)

            # Set new value
            _set_snapshot_value(modified, attr_path, [new_value] if isinstance(new_value, str) else new_value)

            # Record change
            if old_value != new_value:
                changes.append(
                    {
                        "attribute": attr_path,
                        "before": old_value,
                        "after": new_value,
                        "kind": "constraint",
                    }
                )

    return modified, changes


def _apply_constraint_else_effects(
    snapshot: WorldSnapshot,
    constraint: BranchingConstraint,
    registry_manager: RegistryManager,
) -> Tuple[WorldSnapshot, List[ChangeDict]]:
    """Apply constraint else_effects to a snapshot (ELSE branch).

    Supports special effect handling:
    - set_attribute: sets the value directly
    - exclude_values: removes specific values from a value set (via effect.value as list to exclude)
    """
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect

    modified = deepcopy(snapshot)
    changes: List[ChangeDict] = []

    for effect in constraint.else_effects:
        if isinstance(effect, SetAttributeEffect):
            attr_path = effect.target.to_string()
            effect_value = effect.value

            # Get old value
            old_value = modified.get_attribute_value(attr_path)

            # Check if this is an exclusion (value starts with "!" or is a list of exclusions)
            if isinstance(effect_value, str) and effect_value.startswith("!"):
                # Exclude single value
                exclude_val = effect_value[1:]  # Remove the "!" prefix
                if isinstance(old_value, list):
                    new_values = [v for v in old_value if v != exclude_val]
                    if new_values and new_values != old_value:
                        _set_snapshot_value(modified, attr_path, new_values)
                        new_value = new_values[0] if len(new_values) == 1 else new_values
                        changes.append(
                            {
                                "attribute": attr_path,
                                "before": old_value,
                                "after": new_value,
                                "kind": "constraint",
                            }
                        )
            elif isinstance(effect_value, list) and all(isinstance(v, str) and v.startswith("!") for v in effect_value):
                # Exclude multiple values
                exclude_vals = [v[1:] for v in effect_value]  # Remove "!" prefixes
                if isinstance(old_value, list):
                    new_values = [v for v in old_value if v not in exclude_vals]
                    if new_values and new_values != old_value:
                        _set_snapshot_value(modified, attr_path, new_values)
                        new_value = new_values[0] if len(new_values) == 1 else new_values
                        changes.append(
                            {
                                "attribute": attr_path,
                                "before": old_value,
                                "after": new_value,
                                "kind": "constraint",
                            }
                        )
            else:
                # Regular set_attribute
                new_value = effect_value
                _set_snapshot_value(modified, attr_path, [new_value] if isinstance(new_value, str) else new_value)
                if old_value != new_value:
                    changes.append(
                        {
                            "attribute": attr_path,
                            "before": old_value,
                            "after": new_value,
                            "kind": "constraint",
                        }
                    )

    return modified, changes


def _set_snapshot_value(snapshot: WorldSnapshot, attr_path: str, values: List[str]) -> None:
    """Set attribute value in snapshot."""
    attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
    if attr:
        attr.value = values[0] if len(values) == 1 else values


def cleanup_single_value_trends(
    snapshot: WorldSnapshot,
    registry_manager: RegistryManager,
) -> WorldSnapshot:
    """Remove trends from attributes where value set has only one element.

    If a trend results in only one possible value, it doesn't make sense
    to keep the trend active. This function cleans up such cases.

    Args:
        snapshot: The snapshot to clean up
        registry_manager: Registry manager for accessing spaces

    Returns:
        Modified snapshot with cleaned up trends
    """
    modified = deepcopy(snapshot)

    # Process part attributes
    for part_name, part in modified.object_state.parts.items():
        for attr_name, attr in part.attributes.items():
            if attr.trend and attr.trend != "none":
                value = attr.value
                # If value is a single value (not a list) or a list with one element
                if not isinstance(value, list) or len(value) == 1:
                    attr.trend = "none"

    # Process global attributes
    for attr_name, attr in modified.object_state.global_attributes.items():
        if attr.trend and attr.trend != "none":
            value = attr.value
            if not isinstance(value, list) or len(value) == 1:
                attr.trend = "none"

    return modified


def _has_active_trends(snapshot: WorldSnapshot) -> bool:
    """Check if any attribute in the snapshot has an active trend."""
    # Check part attributes
    for part_name, part in snapshot.object_state.parts.items():
        for attr_name, attr in part.attributes.items():
            if attr.trend and attr.trend != "none":
                return True

    # Check global attributes
    for attr_name, attr in snapshot.object_state.global_attributes.items():
        if attr.trend and attr.trend != "none":
            return True

    return False


__all__ = [
    "ConstraintBranchInfo",
    "apply_branching_constraints",
    "cleanup_single_value_trends",
    "get_branching_constraints",
]
