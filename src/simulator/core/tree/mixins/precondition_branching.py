"""Precondition branching mixin for TreeSimulationRunner.

Provides methods for creating branches based on preconditions,
including compound (AND/OR) and nested conditions with De Morgan's law.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.tree.models import BranchCondition
from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

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

        passing_values = [
            v for v in possible_values if evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]
        failing_values = [
            v
            for v in possible_values
            if not evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]

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

        # Only create fail branch(es) if no known value already satisfies the OR
        if not known_satisfies_or:
            # Check if OR contains nested AND conditions
            has_nested_and = any(isinstance(sub, AndCondition) for sub in condition.conditions)

            if has_nested_and:
                # Use De Morgan branching for nested conditions
                # NOT((A AND B) OR C) = (NOT A OR NOT B) AND NOT C
                # This may produce MULTIPLE fail branches
                fail_branches = self._create_demorgan_or_fail_branches(
                    tree=tree,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    condition=condition,
                    instance=instance,
                    layer_state_cache=layer_state_cache,
                )
                branches.extend(fail_branches)
            else:
                # Simple OR: all fail values combined in single node
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

    def _create_demorgan_or_fail_branches(
        self,
        tree: "SimulationTree",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        condition: OrCondition,
        instance: "ObjectInstance",
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """Create multiple fail branches for OR condition with nested AND using De Morgan.

        For NOT((A AND B) OR C):
        - De Morgan gives: (NOT A OR NOT B) AND NOT C
        - This produces multiple fail configs where C always fails,
          and either A or B fails (one branch per failing option)
        """
        from simulator.core.tree.models import NodeStatus
        from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
        from simulator.core.tree.snapshot_utils import snapshot_with_constrained_values

        if layer_state_cache is None:
            layer_state_cache = {}

        parent_snapshot = parent_node.snapshot if parent_node else None

        # Compute all fail configurations using De Morgan
        fail_configs = self._compute_or_fail_configs(condition, instance, parent_snapshot)

        if not fail_configs:
            return []

        branches: List["TreeNode"] = []

        for config in fail_configs:
            if not config:
                continue

            # Create snapshot with these constrained values
            new_snapshot = parent_node.snapshot
            all_changes: List[Dict] = []

            for attr_path, values in config.items():
                new_snapshot, constraint_changes = snapshot_with_constrained_values(
                    new_snapshot, attr_path, values, self.registry_manager
                )
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                all_changes.extend(narrowing)
                for cc in constraint_changes:
                    all_changes.append(
                        {
                            "attribute": cc["attribute"],
                            "before": cc["before"],
                            "after": cc["after"],
                            "kind": cc.get("kind", "constraint"),
                        }
                    )

            error_msg = f"Precondition failed: {condition.describe()}"

            # Create compound branch condition
            branch_condition = self._create_compound_branch_condition_from_config(config, "precondition", "fail", "and")

            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.REJECTED.value,
                error=error_msg,
                branch_condition=branch_condition,
                base_changes=all_changes,
                result_instance=None,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _compute_or_fail_configs(
        self,
        condition: OrCondition,
        instance: "ObjectInstance",
        parent_snapshot: Optional["TreeNode"],
    ) -> List[Dict[str, List[str]]]:
        """Compute all fail configurations for OR condition using De Morgan.

        For NOT(A OR B) = NOT A AND NOT B (combine)
        For nested AND: NOT(A AND B) = NOT A OR NOT B (split)
        """
        from simulator.core.tree.utils.condition_evaluation import (
            evaluate_condition_for_value,
            get_possible_values_for_attribute,
        )

        def compute_fail_for_condition(cond) -> List[Dict[str, List[str]]]:
            """Recursively compute fail configs for a condition."""
            if isinstance(cond, AttributeCondition):
                attr_path = cond.target.to_string()
                possible_values, is_known = get_possible_values_for_attribute(
                    attr_path, instance, parent_snapshot, self.registry_manager
                )
                if not possible_values:
                    return []

                if is_known:
                    if evaluate_condition_for_value(cond, possible_values[0], instance, self.registry_manager):
                        return []  # Known value satisfies, can't fail
                    else:
                        return [{attr_path: possible_values}]

                satisfying = [
                    v for v in possible_values if evaluate_condition_for_value(cond, v, instance, self.registry_manager)
                ]
                complement = [v for v in possible_values if v not in satisfying]

                if not complement:
                    return []  # Always satisfied

                return [{attr_path: complement}]

            elif isinstance(cond, AndCondition):
                # NOT(A AND B) = NOT A OR NOT B -> split into multiple configs
                all_configs: List[Dict[str, List[str]]] = []
                for sub in cond.conditions:
                    sub_configs = compute_fail_for_condition(sub)
                    all_configs.extend(sub_configs)
                return all_configs

            elif isinstance(cond, OrCondition):
                # NOT(A OR B) = NOT A AND NOT B -> combine configs
                sub_config_lists: List[List[Dict[str, List[str]]]] = []
                for sub in cond.conditions:
                    sub_configs = compute_fail_for_condition(sub)
                    if not sub_configs:
                        return []  # This sub can't fail, so OR can't fail
                    sub_config_lists.append(sub_configs)

                if not sub_config_lists:
                    return []

                # Cartesian product of all sub-configs
                combined = sub_config_lists[0]
                for next_configs in sub_config_lists[1:]:
                    new_combined = []
                    for existing in combined:
                        for new_config in next_configs:
                            merged = dict(existing)
                            for attr, vals in new_config.items():
                                if attr in merged:
                                    # Intersect values
                                    merged[attr] = [v for v in merged[attr] if v in vals]
                                    if not merged[attr]:
                                        break
                                else:
                                    merged[attr] = vals
                            else:
                                new_combined.append(merged)
                    combined = new_combined

                return combined

            return []

        return compute_fail_for_condition(condition)

    def _create_compound_branch_condition_from_config(
        self,
        config: Dict[str, List[str]],
        source: str,
        branch_type: str,
        compound_type: str,
    ) -> BranchCondition:
        """Create a BranchCondition from a config dict."""

        from simulator.core.tree.models import BranchCondition

        sub_conditions: List[BranchCondition] = []
        for attr_path, values in config.items():
            operator = "in" if len(values) > 1 else "equals"
            value: Union[str, List[str]] = values if len(values) > 1 else values[0]
            sub_conditions.append(
                BranchCondition(
                    attribute=attr_path,
                    operator=operator,
                    value=value,
                    source=source,
                    branch_type=branch_type,
                )
            )

        if len(sub_conditions) == 1:
            return sub_conditions[0]

        first = sub_conditions[0]
        return BranchCondition(
            attribute=first.attribute,
            operator=first.operator,
            value=first.value,
            source=source,
            branch_type=branch_type,
            compound_type=compound_type,
            sub_conditions=sub_conditions,
        )

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

        # Check for compound postcondition (OR with multiple unknown attrs)
        parent_snapshot = parent_node.snapshot if parent_node else None
        postcond_unknowns = self._get_unknown_postcondition_attributes(action, instance, parent_snapshot)
        has_compound_postcond = self._has_compound_postcondition(action) and len(postcond_unknowns) > 1

        if has_compound_postcond:
            # Handle compound OR postcondition with precondition constraints
            return self._create_precond_with_compound_postcond_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                precond_constraints=attr_constraints,
                layer_state_cache=layer_state_cache,
            )

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

        pass_values = [
            v for v in possible_values if evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]
        fail_values = [
            v
            for v in possible_values
            if not evaluate_condition_for_value(condition, v, instance, self.registry_manager)
        ]

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
