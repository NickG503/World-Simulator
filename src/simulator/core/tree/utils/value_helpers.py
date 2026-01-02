"""
Utility functions for computing satisfying and failing values for conditions.

Consolidates repeated value computation logic from branching mixins.
"""

from typing import TYPE_CHECKING, List, Optional, Type

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.actions.conditions.base import Condition
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.registries.registry_manager import RegistryManager


def get_satisfying_values(
    condition: "AttributeCondition",
    instance: "ObjectInstance",
    registry_manager: "RegistryManager",
) -> List[str]:
    """
    Get all values that satisfy a condition.

    Args:
        condition: The AttributeCondition to evaluate
        instance: Object instance for resolving spaces
        registry_manager: Registry manager for space lookups

    Returns:
        List of values that would satisfy the condition
    """
    attr_path = condition.target.to_string()
    space_id = get_attribute_space_id(instance, attr_path)

    if not space_id:
        return []

    space_values = get_all_space_values(space_id, registry_manager)

    if not space_values:
        return []

    return [v for v in space_values if evaluate_condition_for_value(condition, v, instance, registry_manager)]


def get_failing_values(
    condition: "AttributeCondition",
    instance: "ObjectInstance",
    registry_manager: "RegistryManager",
) -> List[str]:
    """
    Get all values that fail a condition (De Morgan complement).

    Args:
        condition: The AttributeCondition to evaluate
        instance: Object instance for resolving spaces
        registry_manager: Registry manager for space lookups

    Returns:
        List of values that would fail the condition
    """
    attr_path = condition.target.to_string()
    space_id = get_attribute_space_id(instance, attr_path)

    if not space_id:
        return []

    space_values = get_all_space_values(space_id, registry_manager)

    if not space_values:
        return []

    return [v for v in space_values if not evaluate_condition_for_value(condition, v, instance, registry_manager)]


def find_compound_condition_in_effects(
    action: "Action",
    condition_type: Type,
) -> Optional["Condition"]:
    """
    Find first compound condition of given type in action effects.

    Args:
        action: Action to search
        condition_type: Type of condition to find (OrCondition, AndCondition)

    Returns:
        The first matching condition, or None if not found
    """
    from simulator.core.actions.effects.conditional_effects import ConditionalEffect

    for effect in action.effects:
        if isinstance(effect, ConditionalEffect):
            if isinstance(effect.condition, condition_type):
                return effect.condition

    return None


def find_all_compound_conditions_in_effects(
    action: "Action",
) -> tuple[Optional["OrCondition"], Optional["AndCondition"]]:
    """
    Find OR and AND conditions in action effects.

    Returns:
        Tuple of (or_condition, and_condition), either may be None
    """
    from simulator.core.actions.effects.conditional_effects import ConditionalEffect

    or_condition = None
    and_condition = None

    for effect in action.effects:
        if isinstance(effect, ConditionalEffect):
            if isinstance(effect.condition, OrCondition):
                or_condition = effect.condition
            elif isinstance(effect.condition, AndCondition):
                and_condition = effect.condition

    return or_condition, and_condition


def get_condition_values_for_or(
    or_condition: "OrCondition",
    instance: "ObjectInstance",
    registry_manager: "RegistryManager",
) -> List[tuple[str, str, List[str]]]:
    """
    Get satisfying values for each sub-condition in an OR condition.

    Returns:
        List of (attr_path, operator, satisfying_values) tuples
    """
    results = []

    for sub_cond in or_condition.conditions:
        if isinstance(sub_cond, AttributeCondition):
            attr_path = sub_cond.target.to_string()
            satisfying = get_satisfying_values(sub_cond, instance, registry_manager)

            if satisfying:
                results.append((attr_path, sub_cond.operator, satisfying))

    return results


def get_fail_constraints_for_or(
    or_condition: "OrCondition",
    instance: "ObjectInstance",
    registry_manager: "RegistryManager",
) -> dict[str, List[str]]:
    """
    Get failing value constraints for OR condition (De Morgan: all must fail).

    Returns:
        Dict of {attr_path: failing_values}
    """
    constraints = {}

    for sub_cond in or_condition.conditions:
        if isinstance(sub_cond, AttributeCondition):
            attr_path = sub_cond.target.to_string()
            failing = get_failing_values(sub_cond, instance, registry_manager)

            if failing:
                constraints[attr_path] = failing

    return constraints
