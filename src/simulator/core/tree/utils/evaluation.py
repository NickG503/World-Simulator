"""Condition evaluation utilities for tree simulation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import WorldSnapshot


# Cache for space lookups
_space_cache: dict = {}


def evaluate_condition_for_value(condition: Any, value: str, space_levels: Optional[List[str]] = None) -> bool:
    """
    Check if a specific value would pass a condition.

    Args:
        condition: The condition to evaluate
        value: The value to test
        space_levels: Optional ordered list of space values for comparison operators

    Returns:
        True if the condition would pass with this value
    """
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

    if not isinstance(condition, AttributeCondition):
        return True

    op = condition.operator
    expected = condition.value

    if op == "equals":
        return value == expected
    elif op == "not_equals":
        return value != expected
    elif op == "in":
        if isinstance(expected, list):
            return value in expected
        return value == expected
    elif op == "not_in":
        if isinstance(expected, list):
            return value not in expected
        return value != expected
    elif op in ("gt", ">", "lt", "<", "gte", ">=", "lte", "<="):
        # For comparison operators, we need ordered space levels
        if not space_levels:
            # Try to get space levels from the condition's attribute
            space_levels = _get_space_levels_from_condition(condition)

        if not space_levels:
            # Can't evaluate without space levels
            return True

        try:
            value_idx = space_levels.index(value)
            expected_idx = space_levels.index(expected)
        except ValueError:
            return True  # Unknown value, assume pass

        if op in ("gt", ">"):
            return value_idx > expected_idx
        elif op in ("lt", "<"):
            return value_idx < expected_idx
        elif op in ("gte", ">="):
            return value_idx >= expected_idx
        elif op in ("lte", "<="):
            return value_idx <= expected_idx

    return True


def _get_space_levels_from_condition(condition: Any) -> Optional[List[str]]:
    """Try to get space levels from a condition's attribute spec."""
    try:
        # Access the attribute spec if available
        if hasattr(condition, "target") and hasattr(condition.target, "_resolved_spec"):
            spec = condition.target._resolved_spec
            if hasattr(spec, "space_id") and spec.space_id:
                # Return from cache or lookup
                return _space_cache.get(spec.space_id)
    except Exception:
        pass
    return None


def set_space_cache(space_id: str, levels: List[str]) -> None:
    """Set space levels in the cache for comparison operator evaluation."""
    _space_cache[space_id] = levels


def clear_space_cache() -> None:
    """Clear the space cache."""
    _space_cache.clear()


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
