"""
Mixin for De Morgan's law implementation in branching.
"""

from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Tuple

from simulator.core.tree.models import BranchCondition, NodeStatus, TreeNode, WorldSnapshot
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import snapshot_with_constrained_values
from simulator.core.tree.utils.condition_evaluation import (
    evaluate_condition_for_value,
    get_possible_values_for_attribute,
    get_satisfying_values_for_and_condition,
)
from simulator.core.tree.utils.instance_helpers import clone_instance_with_multi_values

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.actions.conditions.base import Condition
    from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree


class DeMorganBranchingMixin:
    """Mixin providing De Morgan's law implementation for compound conditions."""

    def _create_and_condition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "AndCondition",
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """Create branches for an AND condition with potentially multiple unknown attributes.

        For AND:
        - Success branches: ALL attributes constrained to satisfying values
          - If postcond_attr is set, further split by postcondition if/elif/else
        - Fail branches: One per failing disjunct (De Morgan's law)

        Args:
            tree: Simulation tree
            instance: Object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            condition: AndCondition to branch on
            postcond_attr: Optional postcondition attribute for further branching
            layer_state_cache: DAG deduplication cache

        Returns:
            List of branch nodes
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Get satisfying values for all attributes in the AND
        satisfying = get_satisfying_values_for_and_condition(
            condition, instance, parent_node.snapshot, self.registry_manager
        )

        # Check if any attribute has no satisfying values (AND cannot be satisfied)
        if not satisfying or any(not v for v in satisfying.values()):
            # All branches fail
            return self._create_and_fail_branch(
                tree=tree,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                instance=instance,
                layer_state_cache=layer_state_cache,
            )

        branches: List[TreeNode] = []

        # Handle postcondition branching if needed
        if postcond_attr:
            # Get postcondition branch options
            postcond_options = self._get_postcondition_branch_options(action, instance, postcond_attr)

            if postcond_options:
                # Create branches for each postcondition case, with precondition constraints
                for postcond_value, branch_type, effects in postcond_options:
                    # Compute intersection with precondition constraints
                    postcond_values = postcond_value if isinstance(postcond_value, list) else [postcond_value]

                    # Check if postcond_attr is one of the AND-constrained attributes
                    if postcond_attr in satisfying:
                        # Intersect postcondition values with precondition constraints
                        precond_values = satisfying[postcond_attr]
                        intersected = [v for v in postcond_values if v in precond_values]
                        if not intersected:
                            continue  # This postcondition case doesn't overlap with precondition
                        postcond_values = intersected

                    # Build combined attr_values
                    combined_values = dict(satisfying)
                    combined_values[postcond_attr] = postcond_values

                    # Create the branch node
                    node = self._create_and_postcond_branch(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_values=combined_values,
                        postcond_attr=postcond_attr,
                        postcond_values=postcond_values,
                        branch_type=branch_type,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(node)
            else:
                # No simple postcondition - check for compound postcondition
                postcond_compound = self._has_compound_postcondition(action, instance, parent_node.snapshot)
                if postcond_compound:
                    # Compound postcondition - create branches after applying precond constraints
                    compound_cond, compound_effects, compound_unknowns = postcond_compound
                    # Clone instance with precondition constraints
                    modified_instance = clone_instance_with_multi_values(instance, satisfying)
                    postcond_branches = self._create_compound_postcondition_branches(
                        tree=tree,
                        instance=modified_instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        condition=compound_cond,
                        effects=compound_effects,
                        unknowns=compound_unknowns,
                        layer_state_cache=layer_state_cache,
                        precond_attr_values=satisfying,  # Pass precondition constraints
                    )
                    branches.extend(postcond_branches)
                else:
                    # No postcondition branching needed
                    success_node = self._create_and_success_branch(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_values=satisfying,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(success_node)
        else:
            # No simple postcondition attr - check for compound postcondition
            postcond_compound = self._has_compound_postcondition(action, instance, parent_node.snapshot)
            if postcond_compound:
                # Compound postcondition - create branches after applying precond constraints
                compound_cond, compound_effects, compound_unknowns = postcond_compound
                # Clone instance with precondition constraints
                modified_instance = clone_instance_with_multi_values(instance, satisfying)
                postcond_branches = self._create_compound_postcondition_branches(
                    tree=tree,
                    instance=modified_instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    condition=compound_cond,
                    effects=compound_effects,
                    unknowns=compound_unknowns,
                    layer_state_cache=layer_state_cache,
                    precond_attr_values=satisfying,  # Pass precondition constraints
                )
                branches.extend(postcond_branches)
            else:
                # No postcondition branching - single success branch
                success_node = self._create_and_success_branch(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_values=satisfying,
                    layer_state_cache=layer_state_cache,
                )
                branches.append(success_node)

        # Create FAIL branches (one per failing disjunct, by De Morgan's law)
        fail_nodes = self._create_and_fail_branch(
            tree=tree,
            parent_node=parent_node,
            action=action,
            parameters=parameters,
            condition=condition,
            instance=instance,
            layer_state_cache=layer_state_cache,
        )
        branches.extend(fail_nodes)

        return branches

    def _create_and_fail_branch(
        self,
        tree: "SimulationTree",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "AndCondition",
        instance: "ObjectInstance",
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """Create fail branch(es) for AND condition.

        By De Morgan's law: NOT(A ∈ X AND B ∈ Y) = (A ∉ X) OR (B ∉ Y)

        This means we create MULTIPLE fail branches:
        - Fail Branch 1: A ∈ complement(X), B = unknown (all possible values)
        - Fail Branch 2: A = unknown (all possible values), B ∈ complement(Y)

        Each branch represents a distinct world state where the action failed
        for a different reason.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List[TreeNode] = []

        # Get the satisfying values for each attribute (to compute complements)
        satisfying = get_satisfying_values_for_and_condition(
            condition, instance, parent_node.snapshot, self.registry_manager
        )

        # For each attribute, create a fail branch where THAT attribute fails
        # and other attributes remain unknown
        for attr_path, passing_values in satisfying.items():
            # Get possible values for this attribute
            all_values, is_known = get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None, self.registry_manager
            )
            if not all_values:
                continue

            # If value is KNOWN, check if it can fail
            if is_known:
                if all_values[0] in passing_values:
                    # Known value satisfies - no fail branch for this attr
                    continue
                else:
                    # Known value already fails - deterministic failure
                    continue

            # Compute complement: values that FAIL this condition
            complement_values = [v for v in all_values if v not in passing_values]

            if not complement_values:
                continue  # This attribute cannot fail (all values pass)

            # Build the fail state: this attribute = complement, others = unknown
            fail_attr_values: Dict[str, List[str]] = {}
            for other_attr, other_vals in satisfying.items():
                if other_attr == attr_path:
                    fail_attr_values[other_attr] = complement_values
                else:
                    # Other attributes remain at their original unknown state
                    other_values, _ = get_possible_values_for_attribute(
                        other_attr, instance, parent_node.snapshot if parent_node else None, self.registry_manager
                    )
                    if other_values:
                        fail_attr_values[other_attr] = other_values

            # Create snapshot with the failed attribute constrained
            new_snapshot, constraint_changes = snapshot_with_constrained_values(
                parent_node.snapshot, attr_path, complement_values, self.registry_manager
            )

            # Build error message for this specific failure
            error_msg = f"Precondition failed: {attr_path} not in allowed values"

            # Add narrowing changes
            changes = compute_narrowing_change(parent_node.snapshot, attr_path, complement_values)
            for cc in constraint_changes:
                changes.append(
                    {
                        "attribute": cc["attribute"],
                        "before": cc["before"],
                        "after": cc["after"],
                        "kind": cc.get("kind", "constraint"),
                    }
                )

            # Create branch condition for this specific failure
            branch_condition = self._create_simple_branch_condition(
                attr_path, complement_values, "precondition", "fail"
            )

            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.REJECTED.value,
                error=error_msg,
                branch_condition=branch_condition,
                base_changes=changes,
                result_instance=None,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _compute_demorgan_fail_configs(
        self,
        condition: "Condition",
        instance: "ObjectInstance",
        parent_snapshot: Optional[WorldSnapshot],
    ) -> List[Dict[str, List[str]]]:
        """Compute all fail branch configurations by recursively applying De Morgan.

        When De Morgan produces:
        - AND: combine constraints (all attributes in same branch)
        - OR: split into multiple branches (each disjunct becomes a separate branch)

        Returns:
            List of configurations, where each config is {attr_path: complement_values}
            Returns empty list if condition can't fail.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if isinstance(condition, AttributeCondition):
            # Simple condition: return single config with complement values
            attr_path = condition.target.to_string()
            possible_values, is_known = get_possible_values_for_attribute(
                attr_path, instance, parent_snapshot, self.registry_manager
            )

            if not possible_values:
                return []

            if is_known:
                if evaluate_condition_for_value(condition, possible_values[0], instance, self.registry_manager):
                    # Known value satisfies - can't fail
                    return []
                else:
                    # Known value fails - use it
                    return [{attr_path: possible_values}]

            satisfying = [
                v
                for v in possible_values
                if evaluate_condition_for_value(condition, v, instance, self.registry_manager)
            ]
            complement = [v for v in possible_values if v not in satisfying]

            if not complement:
                return []  # Always satisfied, can't fail

            return [{attr_path: complement}]

        elif isinstance(condition, AndCondition):
            # De Morgan: NOT(A AND B) = NOT(A) OR NOT(B)
            # OR means we create multiple branches, one per failing sub-condition
            all_configs: List[Dict[str, List[str]]] = []

            for sub_cond in condition.conditions:
                sub_configs = self._compute_demorgan_fail_configs(sub_cond, instance, parent_snapshot)
                all_configs.extend(sub_configs)

            return all_configs

        elif isinstance(condition, OrCondition):
            # De Morgan: NOT(A OR B) = NOT(A) AND NOT(B)
            # AND means we combine all constraints into each branch
            # We need to compute cross-product of all sub-configs

            sub_config_lists: List[List[Dict[str, List[str]]]] = []

            for sub_cond in condition.conditions:
                sub_configs = self._compute_demorgan_fail_configs(sub_cond, instance, parent_snapshot)
                if not sub_configs:
                    # This sub-condition can't fail, so entire OR can't fail
                    return []
                sub_config_lists.append(sub_configs)

            # Combine: for each combination of sub-configs, merge them
            # Start with first list
            if not sub_config_lists:
                return []

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
                                    # Empty intersection - skip this combo
                                    break
                            else:
                                merged[attr] = vals
                        else:
                            new_combined.append(merged)
                combined = new_combined

            return combined

        return []

    def _create_or_condition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "OrCondition",
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """Create branches for an OR condition with multiple unknown attributes.

        For OR:
        - Multiple success branches, one per disjunct that can be satisfied
        - Each success branch constrains different attributes
        - Fail branch only if NO disjunct can be satisfied

        Args:
            tree: Simulation tree
            instance: Object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            condition: OrCondition to branch on
            postcond_attr: Optional postcondition attribute for further branching
            layer_state_cache: DAG deduplication cache

        Returns:
            List of branch nodes
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List[TreeNode] = []

        # For each disjunct in the OR, create a success branch if it can be satisfied
        # Use get_attribute_conditions() to handle nested compound conditions
        for sub_cond in condition.conditions:
            # Get all attribute conditions from this sub-condition (handles nested AND/OR)
            if isinstance(sub_cond, AttributeCondition):
                attr_conditions = [sub_cond]
            elif hasattr(sub_cond, "get_attribute_conditions"):
                attr_conditions = sub_cond.get_attribute_conditions()
            else:
                continue

            # For each attribute condition, check if it can be satisfied
            for attr_cond in attr_conditions:
                attr_path = attr_cond.target.to_string()
                possible_values, is_known_value = get_possible_values_for_attribute(
                    attr_path, instance, parent_node.snapshot if parent_node else None, self.registry_manager
                )

                if not possible_values:
                    continue

                # Get satisfying values for this condition
                satisfying = [
                    v
                    for v in possible_values
                    if evaluate_condition_for_value(attr_cond, v, instance, self.registry_manager)
                ]

                if satisfying:
                    # If value is already known and satisfies, use it
                    # If known but doesn't satisfy, skip
                    if is_known_value and not satisfying:
                        continue

                    # Create success branch with this attribute constrained
                    success_node = self._create_branch_success_node(
                        tree=tree,
                        instance=instance,
                        parent_node=parent_node,
                        action=action,
                        parameters=parameters,
                        attr_path=attr_path,
                        values=satisfying,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(success_node)

        # Create FAIL branches: when ALL disjuncts fail simultaneously
        # By De Morgan: NOT(A OR B) = NOT(A) AND NOT(B)
        # For nested: NOT((A AND B) OR C) creates multiple branches
        fail_nodes = self._create_or_fail_branches(
            tree=tree,
            parent_node=parent_node,
            action=action,
            parameters=parameters,
            condition=condition,
            instance=instance,
            layer_state_cache=layer_state_cache,
        )
        branches.extend(fail_nodes)

        return branches

    def _create_or_fail_branches(
        self,
        tree: "SimulationTree",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "OrCondition",
        instance: "ObjectInstance",
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """Create fail branch(es) for OR condition using recursive De Morgan.

        By De Morgan's law: NOT(A OR B) = NOT(A) AND NOT(B)
        For nested: NOT((A AND B) OR C) = (NOT(A) OR NOT(B)) AND NOT(C)

        When De Morgan produces OR, we create multiple fail branches.
        When De Morgan produces AND, we combine constraints in same branch.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        parent_snapshot = parent_node.snapshot if parent_node else None

        # Compute all fail configurations
        fail_configs = self._compute_demorgan_fail_configs(condition, instance, parent_snapshot)

        if not fail_configs:
            return []

        branches: List[TreeNode] = []

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

            # Create branch condition (simple or compound AND, never OR at branch level)
            branch_condition = self._create_compound_branch_condition(
                attr_values=config,
                source="precondition",
                branch_type="fail",
                compound_type="and",
            )

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

    def _create_demorgan_branch_condition(
        self,
        condition: "Condition",
        instance: "ObjectInstance",
        parent_snapshot: Optional[WorldSnapshot],
        source: Literal["precondition", "postcondition"],
        branch_type: Literal["if", "elif", "else", "success", "fail"],
    ) -> Optional[BranchCondition]:
        """Create a BranchCondition that represents NOT(condition) using De Morgan's law.

        Recursively applies De Morgan:
        - NOT(A AND B) = NOT(A) OR NOT(B)
        - NOT(A OR B) = NOT(A) AND NOT(B)

        Returns:
            BranchCondition with proper nested structure, or None if condition can't fail
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if isinstance(condition, AttributeCondition):
            # Simple condition: just get the complement values
            attr_path = condition.target.to_string()
            possible_values, is_known = get_possible_values_for_attribute(
                attr_path, instance, parent_snapshot, self.registry_manager
            )

            if not possible_values:
                return None

            # If known, check if it satisfies
            if is_known:
                if evaluate_condition_for_value(condition, possible_values[0], instance, self.registry_manager):
                    # Known value satisfies - can't fail
                    return None
                else:
                    # Known value fails - use it
                    return self._create_simple_branch_condition(attr_path, possible_values, source, branch_type)

            # Get complement (values that FAIL)
            satisfying = [
                v
                for v in possible_values
                if evaluate_condition_for_value(condition, v, instance, self.registry_manager)
            ]
            complement = [v for v in possible_values if v not in satisfying]

            if not complement:
                return None

            return self._create_simple_branch_condition(attr_path, complement, source, branch_type)

        elif isinstance(condition, AndCondition):
            # De Morgan: NOT(A AND B) = NOT(A) OR NOT(B)
            # Each sub-condition's negation becomes a sub-condition, connected by OR
            sub_branch_conditions = []
            for sub_cond in condition.conditions:
                sub_bc = self._create_demorgan_branch_condition(
                    sub_cond, instance, parent_snapshot, source, branch_type
                )
                if sub_bc is not None:
                    sub_branch_conditions.append(sub_bc)

            if not sub_branch_conditions:
                return None
            if len(sub_branch_conditions) == 1:
                return sub_branch_conditions[0]

            return BranchCondition(
                attribute="",
                operator="",
                value="",
                source=source,
                branch_type=branch_type,
                compound_type="or",  # AND flips to OR
                sub_conditions=sub_branch_conditions,
            )

        elif isinstance(condition, OrCondition):
            # De Morgan: NOT(A OR B) = NOT(A) AND NOT(B)
            # Each sub-condition's negation becomes a sub-condition, connected by AND
            sub_branch_conditions = []
            all_can_fail = True

            for sub_cond in condition.conditions:
                sub_bc = self._create_demorgan_branch_condition(
                    sub_cond, instance, parent_snapshot, source, branch_type
                )
                if sub_bc is None:
                    # This sub-condition can't fail, so the whole OR can't fail
                    all_can_fail = False
                    break
                sub_branch_conditions.append(sub_bc)

            if not all_can_fail or not sub_branch_conditions:
                return None
            if len(sub_branch_conditions) == 1:
                return sub_branch_conditions[0]

            return BranchCondition(
                attribute="",
                operator="",
                value="",
                source=source,
                branch_type=branch_type,
                compound_type="and",  # OR flips to AND
                sub_conditions=sub_branch_conditions,
            )

        return None
