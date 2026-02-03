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
from simulator.core.tree.snapshot_utils import compute_value_set_from_trend
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


def _expand_trends_to_value_sets(
    snapshot: WorldSnapshot,
    registry_manager: RegistryManager,
) -> WorldSnapshot:
    """Expand any active trends in the snapshot to value sets.

    This converts single values with trends to value sets representing
    all possible values the attribute could have over time.

    For example, battery.level = "medium" with trend = "down" becomes
    battery.level = ["empty", "low", "medium"]

    Also handles value sets: battery.level = ["low", "medium", "high", "full"]
    with trend = "down" becomes ["empty", "low", "medium", "high", "full"]

    Args:
        snapshot: The current world snapshot
        registry_manager: Registry manager for accessing spaces

    Returns:
        A new snapshot with trends expanded to value sets
    """
    modified = deepcopy(snapshot)

    # Iterate over all parts and attributes
    for part_name, part_data in modified.object_state.parts.items():
        for attr_name, attr_snapshot in part_data.attributes.items():
            trend = attr_snapshot.trend
            if trend and trend != "none":
                current_value = attr_snapshot.value
                space_id = attr_snapshot.space_id

                # Skip if no space defined or value is unknown
                if not space_id or current_value == "unknown":
                    continue

                if isinstance(current_value, list):
                    # Value is already a list - expand each value and union
                    all_values = set()
                    for val in current_value:
                        expanded = compute_value_set_from_trend(val, trend, space_id, registry_manager)
                        all_values.update(expanded)

                    # Sort by space order if possible
                    try:
                        space = registry_manager.spaces.get(space_id)
                        if space:
                            levels = list(space.levels)
                            sorted_values = [v for v in levels if v in all_values]
                        else:
                            sorted_values = sorted(all_values)
                    except Exception:
                        sorted_values = sorted(all_values)

                    # Update if we expanded the value set
                    if len(sorted_values) > len(current_value):
                        attr_snapshot.value = sorted_values
                else:
                    # Single value - compute value set from trend
                    value_set = compute_value_set_from_trend(current_value, trend, space_id, registry_manager)

                    # If we got multiple values, update the snapshot
                    if len(value_set) > 1:
                        attr_snapshot.value = value_set

    return modified


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
    # First, expand any trends to value sets in the snapshot
    expanded_snapshot = _expand_trends_to_value_sets(snapshot, registry_manager)

    constraints = get_branching_constraints(object_type_name, registry_manager)
    if not constraints:
        # No branching constraints - return snapshot with trend cleanup
        cleaned = cleanup_single_value_trends(expanded_snapshot, registry_manager)
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

    # Process all constraints in sequence - each constraint can further split branches
    # Start with the expanded snapshot as the only branch
    current_branches = [(expanded_snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]

    for constraint in constraints:
        next_branches = []
        for branch_snapshot, _ in current_branches:
            # Apply this constraint to each existing branch
            new_branches = _apply_single_branching_constraint(branch_snapshot, constraint, registry_manager)
            next_branches.extend(new_branches)
        current_branches = next_branches

    # If we have branches, return them; otherwise return the original
    if current_branches:
        return current_branches

    return [(expanded_snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]


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
    """Create IF, ELIF, and ELSE branches for a value set.

    When elif_cases are present, non-IF values are matched against each
    elif case individually, creating one branch per matching case.
    Any remaining unmatched values go to the ELSE branch.
    """
    branches: List[Tuple[WorldSnapshot, ConstraintBranchInfo]] = []

    # Split values into matching (IF) and non-matching
    if_values = []
    non_if_values = []

    for val in current_values:
        if _value_matches_condition(val, condition_value, condition_operator):
            if_values.append(val)
        else:
            non_if_values.append(val)

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

    # Check if we have elif_cases to handle non-IF values individually
    if constraint.elif_cases and non_if_values:
        elif_branches = _create_elif_branches(snapshot, constraint, attr_path, non_if_values, registry_manager)
        branches.extend(elif_branches)
    elif non_if_values:
        # No elif_cases — create single ELSE branch (original behavior)
        else_snapshot = deepcopy(snapshot)
        _set_snapshot_value(else_snapshot, attr_path, non_if_values)
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
                    condition_values=non_if_values,
                    has_active_trends=has_trends,
                    changes=else_changes,
                ),
            )
        )

    return branches if branches else [(snapshot, ConstraintBranchInfo(None, "none", "", [], False, []))]


def _create_elif_branches(
    snapshot: WorldSnapshot,
    constraint: BranchingConstraint,
    attr_path: str,
    non_if_values: List[str],
    registry_manager: RegistryManager,
) -> List[Tuple[WorldSnapshot, ConstraintBranchInfo]]:
    """Create individual ELIF branches for non-IF values.

    Each value is tested against elif_cases in order. Values matching an
    elif case get their own branch with that case's effects applied.
    Any remaining unmatched values fall to the ELSE branch.
    """
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

    branches: List[Tuple[WorldSnapshot, ConstraintBranchInfo]] = []
    unmatched_values: List[str] = []

    for val in non_if_values:
        matched = False
        for elif_case in constraint.elif_cases:
            # Check if this value matches the elif condition
            elif_cond = elif_case.condition
            if isinstance(elif_cond, AttributeCondition):
                elif_value = elif_cond.value
                elif_operator = elif_cond.operator
                if _value_matches_condition(val, elif_value, elif_operator):
                    # Create a branch for this value with this elif case's effects
                    elif_snapshot = deepcopy(snapshot)
                    _set_snapshot_value(elif_snapshot, attr_path, [val])
                    elif_modified, elif_changes = _apply_elif_case_effects(elif_snapshot, elif_case, registry_manager)
                    elif_cleaned = cleanup_single_value_trends(elif_modified, registry_manager)
                    has_trends = _has_active_trends(elif_cleaned)
                    branches.append(
                        (
                            elif_cleaned,
                            ConstraintBranchInfo(
                                constraint_name=constraint.name,
                                branch_type="elif",
                                condition_attribute=attr_path,
                                condition_values=[val],
                                has_active_trends=has_trends,
                                changes=elif_changes,
                            ),
                        )
                    )
                    matched = True
                    break  # First matching elif wins

        if not matched:
            unmatched_values.append(val)

    # Create ELSE branch for any remaining unmatched values
    if unmatched_values:
        else_snapshot = deepcopy(snapshot)
        _set_snapshot_value(else_snapshot, attr_path, unmatched_values)
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
                    condition_values=unmatched_values,
                    has_active_trends=has_trends,
                    changes=else_changes,
                ),
            )
        )

    return branches


def _apply_elif_case_effects(
    snapshot: WorldSnapshot,
    elif_case: Any,
    registry_manager: RegistryManager,
) -> Tuple[WorldSnapshot, List[ChangeDict]]:
    """Apply effects from an elif case to a snapshot."""
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect

    modified = deepcopy(snapshot)
    changes: List[ChangeDict] = []

    for effect in elif_case.effects:
        if isinstance(effect, SetAttributeEffect):
            effect_attr_path = effect.target.to_string()
            new_value = effect.value

            # Get old value
            old_value = modified.get_attribute_value(effect_attr_path)

            # Set new value
            _set_snapshot_value(modified, effect_attr_path, [new_value] if isinstance(new_value, str) else new_value)

            # Record change
            if old_value != new_value:
                changes.append(
                    {
                        "attribute": effect_attr_path,
                        "before": old_value,
                        "after": new_value,
                        "kind": "constraint",
                    }
                )

    return modified, changes


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
