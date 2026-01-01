"""Precondition branching mixin for TreeSimulationRunner.

Provides methods for creating branches based on preconditions,
including compound (AND/OR) and nested conditions with De Morgan's law.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
from simulator.core.tree.utils.evaluation import evaluate_condition_for_value

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree, TreeNode


class PreconditionBranchingMixin:
    """Mixin providing precondition branching methods."""

    def _create_precondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
    ) -> List["TreeNode"]:
        """
        Create 2 branches for precondition: success and fail paths.

        Returns:
            List of 2 TreeNodes [success_node, fail_node]
        """
        condition = self._get_precondition_condition(action)
        space_id = get_attribute_space_id(instance, attr_path)

        if not condition or not space_id:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(attr_path)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            possible_values = get_all_space_values(space_id, self.registry_manager)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        passing_values = [v for v in possible_values if evaluate_condition_for_value(condition, v)]
        failing_values = [v for v in possible_values if not evaluate_condition_for_value(condition, v)]

        branches: List["TreeNode"] = []

        if passing_values:
            success_node = self._create_branch_success_node(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_path=attr_path,
                values=passing_values,
            )
            branches.append(success_node)

        if failing_values:
            fail_node = self._create_branch_fail_node(
                tree=tree,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_path=attr_path,
                values=failing_values,
            )
            branches.append(fail_node)

        return branches

    def _create_or_precondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        condition: OrCondition,
        unknowns: List[Tuple[str, AttributeCondition]],
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create branches for OR precondition with unknown attributes.

        OR logic: Action succeeds if ANY sub-condition passes.
        - Creates success branches for each disjunct (handles nested AND/OR)
        - Creates 1 fail branch using De Morgan: NOT(A OR B) = NOT A AND NOT B
        - If any known sub-condition already satisfies the OR, no fail branch is created
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List["TreeNode"] = []
        parent_snapshot = parent_node.snapshot if parent_node else None

        # Check if any known sub-condition already satisfies the OR
        # If so, the OR is guaranteed to pass and we shouldn't create fail branches
        known_satisfies_or = self._check_known_satisfies_or(condition, instance, parent_snapshot)

        for sub_cond in condition.conditions:
            if not self._has_unknown_in_condition(sub_cond, instance, parent_snapshot):
                continue

            pass_constraints = self._get_condition_satisfying_values(sub_cond, instance, parent_snapshot)

            if not pass_constraints:
                continue

            success_branches = self._create_success_branches_for_constraints(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_constraints=pass_constraints,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )
            branches.extend(success_branches)

        # Only create fail branch if no known value already satisfies the OR
        if not known_satisfies_or:
            fail_constraints = self._get_condition_failing_values(condition, instance, parent_snapshot)
            if fail_constraints and all(fail_constraints.values()):
                fail_node = self._create_compound_fail_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_constraints=fail_constraints,
                    compound_type="or",
                    layer_state_cache=layer_state_cache,
                )
                branches.append(fail_node)

        return branches

    def _check_known_satisfies_or(
        self,
        condition: OrCondition,
        instance: "ObjectInstance",
        parent_snapshot: Optional["TreeNode"],
    ) -> bool:
        """Check if any known sub-condition already satisfies the OR."""
        from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id

        for sub_cond in condition.conditions:
            # If sub-condition has unknowns, skip (it's not a known value)
            if self._has_unknown_in_condition(sub_cond, instance, parent_snapshot):
                continue

            # This sub-condition has all known values - check if it passes
            if isinstance(sub_cond, AttributeCondition):
                try:
                    ai = sub_cond.target.resolve(instance)
                    attr_path = sub_cond.target.to_string()
                    current_value = ai.current_value

                    # Get space levels for comparison operators
                    space_id = get_attribute_space_id(instance, attr_path)
                    space_levels = get_all_space_values(space_id, self.registry_manager) if space_id else None

                    if evaluate_condition_for_value(sub_cond, current_value, space_levels):
                        return True  # Known value satisfies this disjunct → OR passes
                except Exception:
                    pass
            elif isinstance(sub_cond, AndCondition):
                # For nested AND, check if all parts are known and satisfy
                all_known_and_pass = self._check_known_and_satisfies(sub_cond, instance, parent_snapshot)
                if all_known_and_pass:
                    return True

        return False

    def _check_known_and_satisfies(
        self,
        condition: AndCondition,
        instance: "ObjectInstance",
        parent_snapshot: Optional["TreeNode"],
    ) -> bool:
        """Check if all parts of an AND are known and satisfy."""
        from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id

        for sub_cond in condition.conditions:
            if self._has_unknown_in_condition(sub_cond, instance, parent_snapshot):
                return False  # Has unknown, can't be definitely satisfied

            if isinstance(sub_cond, AttributeCondition):
                try:
                    ai = sub_cond.target.resolve(instance)
                    attr_path = sub_cond.target.to_string()
                    current_value = ai.current_value

                    space_id = get_attribute_space_id(instance, attr_path)
                    space_levels = get_all_space_values(space_id, self.registry_manager) if space_id else None

                    if not evaluate_condition_for_value(sub_cond, current_value, space_levels):
                        return False  # One part fails, AND fails
                except Exception:
                    return False

        return True  # All parts are known and pass

    def _create_success_branches_for_constraints(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_constraints: Dict[str, List[str]],
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """Create success branches for a set of attribute constraints."""
        if layer_state_cache is None:
            layer_state_cache = {}

        if not attr_constraints:
            return []

        postcond_overlaps = postcond_attr and postcond_attr in attr_constraints

        if postcond_attr and not postcond_overlaps:
            return self._create_and_postcond_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                precond_constraints=attr_constraints,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )
        else:
            if len(attr_constraints) == 1:
                attr_path = list(attr_constraints.keys())[0]
                values = attr_constraints[attr_path]
                return [
                    self._create_branch_success_node(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_path=attr_path,
                        values=values,
                        layer_state_cache=layer_state_cache,
                    )
                ]
            else:
                return [
                    self._create_compound_success_node(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_constraints=attr_constraints,
                        layer_state_cache=layer_state_cache,
                    )
                ]

    def _create_and_precondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        condition: AndCondition,
        unknowns: List[Tuple[str, AttributeCondition]],
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create branches for AND precondition with unknown attributes.

        AND logic: Action succeeds if ALL sub-conditions pass.
        - Creates 1 success branch (all constraints must be satisfied)
        - Creates N fail branches using De Morgan: NOT(A AND B) = NOT A OR NOT B
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List["TreeNode"] = []
        parent_snapshot = parent_node.snapshot if parent_node else None

        pass_constraints = self._get_condition_satisfying_values(condition, instance, parent_snapshot)

        if pass_constraints and all(pass_constraints.values()):
            success_branches = self._create_success_branches_for_constraints(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_constraints=pass_constraints,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )
            branches.extend(success_branches)

        for sub_cond in condition.conditions:
            if not self._has_unknown_in_condition(sub_cond, instance, parent_snapshot):
                continue

            fail_constraints = self._get_condition_failing_values(sub_cond, instance, parent_snapshot)

            if not fail_constraints:
                continue

            if len(fail_constraints) == 1:
                attr_path = list(fail_constraints.keys())[0]
                fail_values = fail_constraints[attr_path]
                if fail_values:
                    fail_node = self._create_branch_fail_node(
                        tree=tree,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_path=attr_path,
                        values=fail_values,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(fail_node)
            else:
                if all(fail_constraints.values()):
                    fail_node = self._create_compound_fail_node(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_constraints=fail_constraints,
                        compound_type="and",
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(fail_node)

        return branches

    def _create_combined_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create branches considering BOTH precondition and postcondition.

        Logic:
        1. Partition values for precondition into pass/fail sets
        2. Create FAIL branch with fail values
        3. For SUCCESS values, further split by postcondition if needed
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        condition = self._get_precondition_condition(action)
        space_id = get_attribute_space_id(instance, precond_attr)

        if not condition or not space_id:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(precond_attr)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            possible_values = get_all_space_values(space_id, self.registry_manager)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        pass_values = [v for v in possible_values if evaluate_condition_for_value(condition, v)]
        fail_values = [v for v in possible_values if not evaluate_condition_for_value(condition, v)]

        branches: List["TreeNode"] = []

        if pass_values:
            if postcond_attr is None:
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
