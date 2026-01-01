"""Condition evaluation utilities for tree simulation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import WorldSnapshot


def evaluate_condition_for_value(condition: Any, value: str) -> bool:
    """
    Check if a specific value would pass a condition.

    Args:
        condition: The condition to evaluate
        value: The value to test

    Returns:
        True if the condition would pass with this value
    """
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

    if not isinstance(condition, AttributeCondition):
        return True

    if condition.operator == "equals":
        return value == condition.value
    elif condition.operator == "not_equals":
        return value != condition.value
    elif condition.operator == "in":
        if isinstance(condition.value, list):
            return value in condition.value
        return value == condition.value
    elif condition.operator == "not_in":
        if isinstance(condition.value, list):
            return value not in condition.value
        return value != condition.value
    elif condition.operator in ("gt", ">"):
        return False  # Simplified for now
    elif condition.operator in ("lt", "<"):
        return False  # Simplified for now
    return True


def get_possible_values_for_attr(
    attr_path: str,
    instance: "ObjectInstance",
    parent_snapshot: Optional["WorldSnapshot"],
) -> List[str]:
    """Get possible values for an attribute from snapshot or space."""
    possible_values: List[str] = []
    if parent_snapshot:
        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
        if isinstance(snapshot_value, list):
            possible_values = list(snapshot_value)
    return possible_values
