"""Condition detection mixin for TreeSimulationRunner.

Provides methods for detecting unknown attributes in preconditions and postconditions,
including compound (AND/OR) and nested conditions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
from simulator.core.tree.utils.evaluation import (
    evaluate_condition_for_value,
    get_possible_values_for_attr,
)

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import WorldSnapshot


class ConditionDetectionMixin:
    """Mixin providing condition detection methods."""

    def _get_unknown_precondition_attribute(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional["WorldSnapshot"] = None
    ) -> Optional[str]:
        """
        Get the unknown attribute in precondition that would cause branching.

        An attribute is considered "unknown" (requiring branching) if:
        - Its current_value is "unknown"
        - It's a value SET (list) in the parent snapshot (e.g., from a trend)

        Returns:
            Attribute path if unknown/multi-valued, None if all known single values
        """
        for condition in action.preconditions:
            if isinstance(condition, (OrCondition, AndCondition)):
                unknown_attr = self._find_unknown_in_compound_condition(condition, instance, parent_snapshot)
                if unknown_attr:
                    return unknown_attr
            elif isinstance(condition, AttributeCondition):
                try:
                    ai = condition.target.resolve(instance)
                    attr_path = condition.target.to_string()

                    if ai.current_value == "unknown":
                        return attr_path

                    if parent_snapshot:
                        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                        if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                            return attr_path
                except Exception:
                    pass
        return None

    def _find_unknown_in_compound_condition(
        self,
        condition: Union[OrCondition, AndCondition],
        instance: "ObjectInstance",
        parent_snapshot: Optional["WorldSnapshot"] = None,
    ) -> Optional[str]:
        """Find the first unknown attribute in a compound condition."""
        for sub_cond in condition.conditions:
            if isinstance(sub_cond, (OrCondition, AndCondition)):
                result = self._find_unknown_in_compound_condition(sub_cond, instance, parent_snapshot)
                if result:
                    return result
            elif isinstance(sub_cond, AttributeCondition):
                try:
                    ai = sub_cond.target.resolve(instance)
                    attr_path = sub_cond.target.to_string()

                    if ai.current_value == "unknown":
                        return attr_path

                    if parent_snapshot:
                        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                        if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                            return attr_path
                except Exception:
                    pass
        return None

    def _get_compound_precondition(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional["WorldSnapshot"] = None
    ) -> Optional[Tuple[Union[OrCondition, AndCondition], List[Tuple[str, AttributeCondition]]]]:
        """
        Detect if the precondition is a compound OR/AND condition with unknown attributes.

        Returns:
            Tuple of (compound_condition, list of (attr_path, sub_condition) for unknowns)
            or None if no compound condition with unknowns
        """
        for condition in action.preconditions:
            if isinstance(condition, (OrCondition, AndCondition)):
                unknowns = self._get_unknown_attrs_in_compound_flat(condition, instance, parent_snapshot)
                if unknowns:
                    return (condition, unknowns)
        return None

    def _get_unknown_attrs_in_compound_flat(
        self,
        condition: Union[OrCondition, AndCondition],
        instance: "ObjectInstance",
        parent_snapshot: Optional["WorldSnapshot"] = None,
    ) -> List[Tuple[str, AttributeCondition]]:
        """Get all unknown attributes in a compound condition (flattened list)."""
        unknowns: List[Tuple[str, AttributeCondition]] = []

        for sub_cond in condition.conditions:
            if isinstance(sub_cond, (OrCondition, AndCondition)):
                unknowns.extend(self._get_unknown_attrs_in_compound_flat(sub_cond, instance, parent_snapshot))
            elif isinstance(sub_cond, AttributeCondition):
                try:
                    ai = sub_cond.target.resolve(instance)
                    attr_path = sub_cond.target.to_string()

                    if ai.current_value == "unknown":
                        unknowns.append((attr_path, sub_cond))
                    elif parent_snapshot:
                        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                        if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                            unknowns.append((attr_path, sub_cond))
                except Exception:
                    pass

        return unknowns

    def _has_unknown_in_condition(
        self,
        condition: Any,
        instance: "ObjectInstance",
        parent_snapshot: Optional["WorldSnapshot"] = None,
    ) -> bool:
        """Check if a condition (simple or compound) has any unknown attributes."""
        if isinstance(condition, (OrCondition, AndCondition)):
            return any(self._has_unknown_in_condition(sub, instance, parent_snapshot) for sub in condition.conditions)
        elif isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()
                if ai.current_value == "unknown":
                    return True
                if parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                        return True
            except Exception:
                pass
        return False

    def _get_condition_satisfying_values(
        self,
        condition: Any,
        instance: "ObjectInstance",
        parent_snapshot: Optional["WorldSnapshot"] = None,
    ) -> Dict[str, List[str]]:
        """
        Get satisfying values for all unknown attributes in a condition.

        For nested conditions, this computes the intersection (AND) or union (OR)
        of satisfying values based on the condition structure.

        Returns:
            Dict mapping attr_path to list of satisfying values
        """
        if isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()

                is_unknown = ai.current_value == "unknown"
                if not is_unknown and parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    is_unknown = isinstance(snapshot_value, list) and len(snapshot_value) > 1

                if not is_unknown:
                    return {}

                possible_values = get_possible_values_for_attr(attr_path, instance, parent_snapshot)
                space_id = get_attribute_space_id(instance, attr_path)
                space_levels: Optional[List[str]] = None
                if space_id:
                    space_levels = get_all_space_values(space_id, self.registry_manager)
                    if not possible_values:
                        possible_values = space_levels

                if not possible_values:
                    return {}

                pass_values = [v for v in possible_values if evaluate_condition_for_value(condition, v, space_levels)]
                return {attr_path: pass_values} if pass_values else {}
            except Exception:
                return {}

        elif isinstance(condition, AndCondition):
            result: Dict[str, List[str]] = {}
            for sub_cond in condition.conditions:
                sub_values = self._get_condition_satisfying_values(sub_cond, instance, parent_snapshot)
                for attr_path, values in sub_values.items():
                    if attr_path in result:
                        result[attr_path] = [v for v in result[attr_path] if v in values]
                    else:
                        result[attr_path] = values
            return result

        elif isinstance(condition, OrCondition):
            result: Dict[str, List[str]] = {}
            for sub_cond in condition.conditions:
                sub_values = self._get_condition_satisfying_values(sub_cond, instance, parent_snapshot)
                for attr_path, values in sub_values.items():
                    if attr_path in result:
                        result[attr_path] = list(set(result[attr_path]) | set(values))
                    else:
                        result[attr_path] = values
            return result

        return {}

    def _get_condition_failing_values(
        self,
        condition: Any,
        instance: "ObjectInstance",
        parent_snapshot: Optional["WorldSnapshot"] = None,
    ) -> Dict[str, List[str]]:
        """
        Get failing values for all unknown attributes in a condition.

        Uses De Morgan's law:
        - NOT(A AND B) = NOT A OR NOT B
        - NOT(A OR B) = NOT A AND NOT B

        Returns:
            Dict mapping attr_path to list of failing values
        """
        if isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()

                is_unknown = ai.current_value == "unknown"
                if not is_unknown and parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    is_unknown = isinstance(snapshot_value, list) and len(snapshot_value) > 1

                if not is_unknown:
                    return {}

                possible_values = get_possible_values_for_attr(attr_path, instance, parent_snapshot)
                space_id = get_attribute_space_id(instance, attr_path)
                space_levels: Optional[List[str]] = None
                if space_id:
                    space_levels = get_all_space_values(space_id, self.registry_manager)
                    if not possible_values:
                        possible_values = space_levels

                if not possible_values:
                    return {}

                fail_values = [
                    v for v in possible_values if not evaluate_condition_for_value(condition, v, space_levels)
                ]
                return {attr_path: fail_values} if fail_values else {}
            except Exception:
                return {}

        elif isinstance(condition, AndCondition):
            result: Dict[str, List[str]] = {}
            for sub_cond in condition.conditions:
                sub_fail = self._get_condition_failing_values(sub_cond, instance, parent_snapshot)
                for attr_path, values in sub_fail.items():
                    if attr_path in result:
                        result[attr_path] = list(set(result[attr_path]) | set(values))
                    else:
                        result[attr_path] = values
            return result

        elif isinstance(condition, OrCondition):
            result: Dict[str, List[str]] = {}
            for sub_cond in condition.conditions:
                sub_fail = self._get_condition_failing_values(sub_cond, instance, parent_snapshot)
                for attr_path, values in sub_fail.items():
                    if attr_path in result:
                        result[attr_path] = [v for v in result[attr_path] if v in values]
                    else:
                        result[attr_path] = values
            return result

        return {}

    def _get_unknown_postcondition_attribute(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional["WorldSnapshot"] = None
    ) -> Optional[str]:
        """
        Get the unknown attribute in postcondition that would cause branching.

        Returns:
            Attribute path if unknown/multi-valued, None if all known single values
        """
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                cond = effect.condition
                if isinstance(cond, AttributeCondition):
                    try:
                        ai = cond.target.resolve(instance)
                        attr_path = cond.target.to_string()

                        if ai.current_value == "unknown":
                            return attr_path

                        if parent_snapshot:
                            snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                            if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                                return attr_path
                    except Exception:
                        pass
        return None

    def _get_precondition_condition(self, action: "Action") -> Optional[AttributeCondition]:
        """Get the first precondition condition that checks an attribute."""
        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                return condition
        return None

    def _get_postcondition_branch_options(
        self, action: "Action", instance: "ObjectInstance", attribute_path: str
    ) -> List[Tuple[Union[str, List[str]], str, List[Any]]]:
        """
        Get all possible branch options for a postcondition attribute.

        Returns list of (value, branch_type, effects) tuples.
        """
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        options: List[Tuple[Union[str, List[str]], str, List[Any]]] = []
        used_values: set = set()

        all_values: List[str] = []
        try:
            parts = attribute_path.split(".")
            if len(parts) == 2:
                part_name, attr_name = parts
                part_inst = instance.parts.get(part_name)
                if part_inst:
                    attr_inst = part_inst.attributes.get(attr_name)
                    if attr_inst and attr_inst.spec.space_id:
                        space = self.registry_manager.spaces.get(attr_inst.spec.space_id)
                        if space:
                            all_values = list(space.levels)
        except Exception:
            pass

        conditional_index = 0
        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                cond = effect.condition
                if isinstance(cond, AttributeCondition) and cond.target.to_string() == attribute_path:
                    branch_type = "if" if conditional_index == 0 else "elif"
                    conditional_index += 1

                    then_effects = effect.then_effect if isinstance(effect.then_effect, list) else [effect.then_effect]

                    if cond.operator == "equals":
                        value = cond.value
                        options.append((value, branch_type, then_effects))
                        used_values.add(value)
                    elif cond.operator == "in" and isinstance(cond.value, list):
                        value = cond.value
                        options.append((value, branch_type, then_effects))
                        used_values.update(cond.value)

        if all_values and used_values:
            remaining = [v for v in all_values if v not in used_values]
            if remaining:
                options.append((remaining, "else", []))

        return options
