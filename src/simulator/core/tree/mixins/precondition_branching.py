"""
Mixin for precondition analysis and branching.
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from simulator.core.tree.models import TreeNode, WorldSnapshot
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
from simulator.core.tree.utils.condition_evaluation import (
    evaluate_condition_for_value,
)

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree


class PreconditionBranchingMixin:
    """Mixin providing methods for precondition analysis and branching."""

    def _get_unknown_precondition_attribute(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional[WorldSnapshot] = None
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
            unknown = self._find_unknown_in_condition(condition, instance, parent_snapshot)
            if unknown:
                return unknown
        return None

    def _find_unknown_in_condition(
        self,
        condition,
        instance: "ObjectInstance",
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> Optional[str]:
        """Recursively find unknown attributes in a condition (including compound)."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()

                # Check if current value is "unknown"
                if ai.current_value == "unknown":
                    return attr_path

                # Check if parent snapshot has a value set for this attribute
                if parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                        return attr_path
            except Exception:
                pass
        elif isinstance(condition, (AndCondition, OrCondition)):
            # Check all sub-conditions
            for sub_cond in condition.conditions:
                unknown = self._find_unknown_in_condition(sub_cond, instance, parent_snapshot)
                if unknown:
                    return unknown
        return None

    def _get_unknown_attributes_in_condition(
        self,
        condition,
        instance: "ObjectInstance",
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> List[Tuple[str, "AttributeCondition"]]:
        """Get ALL unknown attributes in a condition (for compound conditions).

        Returns list of (attr_path, condition) tuples for all unknown attributes.
        """
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        unknowns: List[Tuple[str, AttributeCondition]] = []

        if isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()

                is_unknown = ai.current_value == "unknown"
                if not is_unknown and parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    is_unknown = isinstance(snapshot_value, list) and len(snapshot_value) > 1

                if is_unknown:
                    unknowns.append((attr_path, condition))
            except Exception:
                pass
        elif isinstance(condition, (AndCondition, OrCondition)):
            for sub_cond in condition.conditions:
                unknowns.extend(self._get_unknown_attributes_in_condition(sub_cond, instance, parent_snapshot))

        return unknowns

    def _get_precondition_condition(self, action: "Action"):
        """Get the first precondition condition that checks an attribute (or compound)."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        for condition in action.preconditions:
            if isinstance(condition, (AttributeCondition, AndCondition, OrCondition)):
                return condition
        return None

    def _create_combined_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """
        Create branches considering BOTH precondition and postcondition.

        Logic:
        1. Partition values for precondition into pass/fail sets
        2. Create FAIL branch with fail values (no effects applied)
        3. For SUCCESS values, further split by postcondition if/elif/else:
           - If postcond_attr is None: single success branch
           - If postcond_attr == precond_attr: intersect with pass values
           - If postcond_attr != precond_attr: split by postcondition cases

        For AND conditions with multiple unknown attributes:
        - Success branch constrains ALL attributes to satisfying values
        - Fail branch keeps original state (action rejected)

        Uses layer_state_cache for DAG deduplication.

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            precond_attr: Attribute path checked in precondition (first unknown)
            postcond_attr: Attribute path checked in postcondition (may be None or same)
            layer_state_cache: Optional cache for deduplication

        Returns:
            List of branches: 1 fail + N success sub-branches
        """
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if layer_state_cache is None:
            layer_state_cache = {}
        condition = self._get_precondition_condition(action)

        if not condition:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Handle AND conditions with multiple attributes
        if isinstance(condition, AndCondition):
            return self._create_and_condition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )

        # Handle OR conditions (creates multiple success branches)
        if isinstance(condition, OrCondition):
            return self._create_or_condition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )

        # Simple AttributeCondition - original logic
        space_id = get_attribute_space_id(instance, precond_attr)

        if not space_id:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Get possible values from parent snapshot or space
        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(precond_attr)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            possible_values = get_all_space_values(space_id, self.registry_manager)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Partition into passing and failing values
        pass_values = [
            v for v in possible_values if evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]
        fail_values = [
            v
            for v in possible_values
            if not evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]

        branches: List[TreeNode] = []

        # 1. Create SUCCESS branches first (so they're primary in current_path)
        if pass_values:
            if postcond_attr is None:
                # No postcondition branching - single success branch
                success_node = self._create_branch_success_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_path=precond_attr,
                    values=pass_values,
                    layer_state_cache=layer_state_cache,
                )
                branches.append(success_node)
            else:
                # Further split by postcondition
                success_branches = self._create_postcondition_success_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    precond_attr=precond_attr,
                    precond_pass_values=pass_values,
                    postcond_attr=postcond_attr,
                    layer_state_cache=layer_state_cache,
                )
                branches.extend(success_branches)

        # 2. Create FAIL branch (if any fail values)
        if fail_values:
            fail_node = self._create_branch_fail_node(
                tree=tree,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_path=precond_attr,
                values=fail_values,
                layer_state_cache=layer_state_cache,
            )
            branches.append(fail_node)

        return branches
