"""
Utility functions for evaluating conditions against specific values.
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.tree.models import WorldSnapshot
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id

if TYPE_CHECKING:
    from simulator.core.actions.conditions.base import Condition
    from simulator.core.registries.registry_manager import RegistryManager


def evaluate_condition_for_value(
    condition,
    value: str,
    instance: Optional[ObjectInstance] = None,
    registry_manager: Optional["RegistryManager"] = None,
) -> bool:
    """
    Check if a specific value would pass a condition.

    Args:
        condition: The condition to evaluate
        value: The value to test
        instance: Optional object instance for resolving qualitative spaces
        registry_manager: Optional registry manager for space lookups

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
        # Check if value is in the list
        if isinstance(condition.value, list):
            return value in condition.value
        return value == condition.value
    elif condition.operator == "not_in":
        # Check if value is NOT in the list
        if isinstance(condition.value, list):
            return value not in condition.value
        return value != condition.value
    elif condition.operator in ("gt", "gte", "lt", "lte"):
        # For qualitative spaces, compare by order using the space
        if instance is None or registry_manager is None:
            return False
        try:
            ai = condition.target.resolve(instance)
            space = registry_manager.spaces.get(ai.spec.space_id)
            if space:
                satisfying_values = space.get_values_for_comparison(str(condition.value), condition.operator)
                return value in satisfying_values
        except (ValueError, AttributeError):
            pass
        return False
    return True


def get_possible_values_for_attribute(
    attr_path: str,
    instance: ObjectInstance,
    parent_snapshot: Optional[WorldSnapshot],
    registry_manager: "RegistryManager",
) -> Tuple[List[str], bool]:
    """Get possible values for an attribute from snapshot or space.

    Returns:
        Tuple of (possible_values, is_known_value)
        - possible_values: List of possible values
        - is_known_value: True if the value is definitively known (single value)
    """
    space_id = get_attribute_space_id(instance, attr_path)
    if not space_id:
        return [], False

    possible_values: List[str] = []
    is_known_value = False

    if parent_snapshot:
        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
        if isinstance(snapshot_value, list):
            possible_values = list(snapshot_value)
        elif isinstance(snapshot_value, str) and snapshot_value != "unknown":
            # Known value
            possible_values = [snapshot_value]
            is_known_value = True

    if not possible_values:
        possible_values = get_all_space_values(space_id, registry_manager)

    return possible_values, is_known_value


def get_satisfying_values_for_condition(
    condition: "Condition",
    instance: ObjectInstance,
    parent_snapshot: Optional[WorldSnapshot],
    registry_manager: "RegistryManager",
) -> Dict[str, List[str]]:
    """Get satisfying values for each attribute in any condition (simple or compound).

    Recursively handles nested AND/OR conditions by flattening to AttributeConditions.

    Args:
        condition: Any condition (AttributeCondition, AndCondition, OrCondition)
        instance: Object instance for space resolution
        parent_snapshot: Parent snapshot for value sets
        registry_manager: Registry manager for space lookups

    Returns:
        Dict mapping attr_path -> list of satisfying values
    """
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.actions.conditions.logical_conditions import (
        AndCondition,
        OrCondition,
    )

    result: Dict[str, List[str]] = {}

    # Get all attribute conditions (flattened from any nested structure)
    if isinstance(condition, AttributeCondition):
        attr_conditions = [condition]
    elif isinstance(condition, (AndCondition, OrCondition)):
        attr_conditions = condition.get_attribute_conditions()
    else:
        return result

    for sub_cond in attr_conditions:
        attr_path = sub_cond.target.to_string()
        possible_values, _ = get_possible_values_for_attribute(attr_path, instance, parent_snapshot, registry_manager)

        if not possible_values:
            continue

        # Filter to values that satisfy this sub-condition
        satisfying = [
            v for v in possible_values if evaluate_condition_for_value(sub_cond, v, instance, registry_manager)
        ]

        if attr_path in result:
            # Intersect with existing values for this attribute
            result[attr_path] = [v for v in result[attr_path] if v in satisfying]
        else:
            result[attr_path] = satisfying

    return result


def get_satisfying_values_for_and_condition(
    condition,
    instance: ObjectInstance,
    parent_snapshot: Optional[WorldSnapshot],
    registry_manager: "RegistryManager",
) -> Dict[str, List[str]]:
    """Get satisfying values for each attribute in an AND condition.

    For AND conditions, we need to find values that satisfy each sub-condition.
    """
    return get_satisfying_values_for_condition(condition, instance, parent_snapshot, registry_manager)
