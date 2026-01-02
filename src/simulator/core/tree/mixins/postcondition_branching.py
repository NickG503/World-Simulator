"""Postcondition branching mixin for TreeSimulationRunner.

Provides methods for creating branches based on postconditions
and Cartesian product with preconditions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from simulator.core.attributes import AttributePath
from simulator.core.tree.models import BranchCondition, NodeStatus
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import capture_snapshot, capture_snapshot_with_values

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree, TreeNode, WorldSnapshot


class PostconditionBranchingMixin:
    """Mixin providing postcondition branching methods."""

    def _create_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        parent_snapshot: Optional["WorldSnapshot"] = None,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create N+1 branches for postcondition: one for each if/elif case + else.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        options = self._get_postcondition_branch_options(action, instance, attr_path)

        if not options:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        constrained_values: Optional[List[str]] = None
        if parent_snapshot:
            snapshot_value = parent_snapshot.get_attribute_value(attr_path)
            if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                constrained_values = list(snapshot_value)

        branches: List["TreeNode"] = []
        used_values: set = set()

        for value, branch_type, effects in options:
            if constrained_values is not None:
                if isinstance(value, list):
                    filtered_value = [v for v in value if v in constrained_values]
                    if not filtered_value:
                        continue
                    value = filtered_value if len(filtered_value) > 1 else filtered_value[0]
                else:
                    if value not in constrained_values:
                        continue

            if isinstance(value, list):
                used_values.update(value)
            else:
                used_values.add(value)

            node = self._create_branch_case_node(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_path=attr_path,
                value=value,
                branch_type=branch_type,
                effects=effects,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _create_postcondition_success_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        precond_pass_values: List[str],
        postcond_attr: str,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create N branches for postcondition, constrained by precondition pass values.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        postcond_cases = self._get_postcondition_branch_options(action, instance, postcond_attr)

        if not postcond_cases:
            return [
                self._create_branch_success_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_path=precond_attr,
                    values=precond_pass_values,
                    layer_state_cache=layer_state_cache,
                )
            ]

        same_attribute = precond_attr == postcond_attr
        branches: List["TreeNode"] = []
        used_postcond_values: set = set()

        for case_value, branch_type, effects in postcond_cases:
            if same_attribute:
                if isinstance(case_value, list):
                    branch_values = [v for v in case_value if v in precond_pass_values]
                    constrained_postcond_value = (
                        branch_values if len(branch_values) > 1 else (branch_values[0] if branch_values else None)
                    )
                else:
                    branch_values = [case_value] if case_value in precond_pass_values else []
                    constrained_postcond_value = case_value if branch_values else None

                if not branch_values:
                    continue
            else:
                branch_values = precond_pass_values
                constrained_postcond_value = case_value

            if same_attribute:
                if isinstance(case_value, list):
                    used_postcond_values.update(case_value)
                else:
                    used_postcond_values.add(case_value)

            node = self._create_postcond_case_node(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                precond_attr=precond_attr,
                precond_values=branch_values,
                postcond_attr=postcond_attr,
                postcond_value=constrained_postcond_value,
                branch_type=branch_type,
                effects=effects,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _create_postcond_case_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        precond_values: List[str],
        postcond_attr: str,
        postcond_value: Union[str, List[str]],
        branch_type: str,
        effects: List[Any],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a node for a postcondition case with effects applied."""
        if layer_state_cache is None:
            layer_state_cache = {}

        new_instance = deepcopy(instance)

        if precond_attr == postcond_attr:
            if isinstance(postcond_value, list):
                self._set_attribute_value(new_instance, precond_attr, postcond_value[0])
            else:
                self._set_attribute_value(new_instance, precond_attr, postcond_value)
        else:
            self._set_attribute_value(new_instance, precond_attr, precond_values[0])
            if isinstance(postcond_value, list):
                self._set_attribute_value(new_instance, postcond_attr, postcond_value[0])
            else:
                self._set_attribute_value(new_instance, postcond_attr, postcond_value)

        action_result = self.engine.apply_action(new_instance, action, parameters)
        raw_changes = action_result.changes if action_result else []

        changes = self._build_changes_list(raw_changes)

        narrowing = compute_narrowing_change(parent_node.snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            postcond_vals = postcond_value if isinstance(postcond_value, list) else [postcond_value]
            narrowing.extend(compute_narrowing_change(parent_node.snapshot, postcond_attr, postcond_vals))
        changes = narrowing + changes

        result_instance = action_result.after if action_result and action_result.after else new_instance

        snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        self._update_snapshot_attribute(snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            if isinstance(postcond_value, list):
                self._update_snapshot_attribute(snapshot, postcond_attr, postcond_value)
            else:
                self._update_snapshot_attribute(snapshot, postcond_attr, [postcond_value])

        # Normalize value and operator for consistent display
        if isinstance(postcond_value, list):
            if len(postcond_value) == 1:
                # Single-item list: unwrap to string and use "equals"
                postcond_display = postcond_value[0]
                operator = "equals"
            else:
                # Multi-item list: keep as list and use "in"
                postcond_display = postcond_value
                operator = "in"
        else:
            postcond_display = postcond_value
            operator = "equals"

        branch_condition = BranchCondition(
            attribute=postcond_attr,
            operator=operator,
            value=postcond_display,
            source="postcondition",
            branch_type=branch_type,
        )

        return create_or_merge_node(
            tree=tree,
            parent_node=parent_node,
            snapshot=snapshot,
            action_name=action.name,
            parameters=parameters,
            status=NodeStatus.OK.value,
            error=None,
            branch_condition=branch_condition,
            base_changes=changes,
            result_instance=result_instance,
            layer_state_cache=layer_state_cache,
        )

    def _create_precond_with_compound_postcond_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        precond_constraints: Dict[str, List[str]],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create branches for precondition success + compound OR postcondition.

        For each precondition success constraint set, create branches for:
        - Each disjunct in the postcondition OR (success)
        - ELSE branch (all disjuncts fail)
        """
        from copy import deepcopy

        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect
        from simulator.core.tree.models import BranchCondition, NodeStatus
        from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
        from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
        from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List["TreeNode"] = []

        # Find the compound OR postcondition
        or_condition = None
        else_condition = None

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                if isinstance(effect.condition, OrCondition):
                    or_condition = effect.condition
                elif isinstance(effect.condition, AndCondition):
                    else_condition = effect.condition

        if not or_condition:
            # No compound OR, create simple success node
            return [
                self._create_compound_success_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_constraints=precond_constraints,
                    layer_state_cache=layer_state_cache,
                )
            ]

        # Create success branches for each disjunct in the OR
        for sub_cond in or_condition.conditions:
            if isinstance(sub_cond, AttributeCondition):
                postcond_attr = sub_cond.target.to_string()

                # Get satisfying values for this condition
                space_id = get_attribute_space_id(instance, postcond_attr)
                space_values = get_all_space_values(space_id, self.registry_manager)

                satisfying_values = []
                for v in space_values:
                    if evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager):
                        satisfying_values.append(v)

                if not satisfying_values:
                    continue

                # Create branch for this disjunct
                for val in satisfying_values:
                    modified_instance = deepcopy(instance)

                    # Apply precondition constraints
                    for attr_path, values in precond_constraints.items():
                        if values:
                            AttributePath.parse(attr_path).set_value_in_instance(modified_instance, values[0])

                    # Apply postcondition value
                    AttributePath.parse(postcond_attr).set_value_in_instance(modified_instance, val)

                    # Apply action
                    result = self.engine.apply_action(modified_instance, action, parameters)
                    changes = self._build_changes_list(result.changes)

                    # Add narrowing changes for precond constraints
                    for attr_path, values in precond_constraints.items():
                        narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                        changes = changes + narrowing

                    # Add narrowing for postcond
                    narrowing = compute_narrowing_change(parent_node.snapshot, postcond_attr, [val])
                    changes = changes + narrowing

                    # Capture snapshot
                    new_snapshot = self._capture_snapshot(result.after, parent_node.snapshot)
                    for attr_path, values in precond_constraints.items():
                        new_snapshot, _ = self._snapshot_with_constrained_values(
                            new_snapshot, attr_path, values, self.registry_manager
                        )
                    new_snapshot, _ = self._snapshot_with_constrained_values(
                        new_snapshot, postcond_attr, [val], self.registry_manager
                    )

                    # Build combined branch condition
                    sub_conditions = []
                    for attr_path, values in precond_constraints.items():
                        op = "in" if len(values) > 1 else "equals"
                        value = values if len(values) > 1 else values[0]
                        sub_conditions.append(
                            BranchCondition(
                                attribute=attr_path,
                                operator=op,
                                value=value,
                                source="precondition",
                                branch_type="success",
                            )
                        )
                    sub_conditions.append(
                        BranchCondition(
                            attribute=postcond_attr,
                            operator="equals",
                            value=val,
                            source="postcondition",
                            branch_type="if",
                        )
                    )

                    if len(sub_conditions) == 1:
                        branch_condition = sub_conditions[0]
                    else:
                        first = sub_conditions[0]
                        branch_condition = BranchCondition(
                            attribute=first.attribute,
                            operator=first.operator,
                            value=first.value,
                            source="precondition",
                            branch_type="success",
                            compound_type="and",
                            sub_conditions=sub_conditions,
                        )

                    node = create_or_merge_node(
                        tree=tree,
                        parent_node=parent_node,
                        snapshot=new_snapshot,
                        action_name=action.name,
                        parameters=parameters,
                        status=NodeStatus.OK.value,
                        error=None,
                        branch_condition=branch_condition,
                        base_changes=changes,
                        result_instance=result.after,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(node)

        # Create ELSE branch (all disjuncts fail)
        if else_condition:
            modified_instance = deepcopy(instance)

            # Apply precondition constraints
            for attr_path, values in precond_constraints.items():
                if values:
                    AttributePath.parse(attr_path).set_value_in_instance(modified_instance, values[0])

            # Collect fail values for all postcond attrs
            all_fail_constraints = {}
            for sub_cond in or_condition.conditions:
                if isinstance(sub_cond, AttributeCondition):
                    postcond_attr = sub_cond.target.to_string()
                    space_id = get_attribute_space_id(instance, postcond_attr)
                    space_values = get_all_space_values(space_id, self.registry_manager)

                    fail_values = []
                    for v in space_values:
                        if not evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager):
                            fail_values.append(v)

                    if fail_values:
                        all_fail_constraints[postcond_attr] = fail_values
                        AttributePath.parse(postcond_attr).set_value_in_instance(modified_instance, fail_values[0])

            # Apply action
            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = self._build_changes_list(result.changes)

            # Add narrowing changes
            for attr_path, values in precond_constraints.items():
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                changes = changes + narrowing
            for attr_path, values in all_fail_constraints.items():
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                changes = changes + narrowing

            # Capture snapshot
            new_snapshot = self._capture_snapshot(result.after, parent_node.snapshot)
            for attr_path, values in precond_constraints.items():
                new_snapshot, _ = self._snapshot_with_constrained_values(
                    new_snapshot, attr_path, values, self.registry_manager
                )
            for attr_path, values in all_fail_constraints.items():
                new_snapshot, _ = self._snapshot_with_constrained_values(
                    new_snapshot, attr_path, values, self.registry_manager
                )

            # Build combined branch condition
            sub_conditions = []
            for attr_path, values in precond_constraints.items():
                op = "in" if len(values) > 1 else "equals"
                value = values if len(values) > 1 else values[0]
                sub_conditions.append(
                    BranchCondition(
                        attribute=attr_path,
                        operator=op,
                        value=value,
                        source="precondition",
                        branch_type="success",
                    )
                )
            for attr_path, values in all_fail_constraints.items():
                op = "in" if len(values) > 1 else "equals"
                value = values if len(values) > 1 else values[0]
                sub_conditions.append(
                    BranchCondition(
                        attribute=attr_path,
                        operator=op,
                        value=value,
                        source="postcondition",
                        branch_type="else",
                    )
                )

            if len(sub_conditions) == 1:
                branch_condition = sub_conditions[0]
            else:
                first = sub_conditions[0]
                branch_condition = BranchCondition(
                    attribute=first.attribute,
                    operator=first.operator,
                    value=first.value,
                    source="precondition",
                    branch_type="success",
                    compound_type="and",
                    sub_conditions=sub_conditions,
                )

            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.OK.value,
                error=None,
                branch_condition=branch_condition,
                base_changes=changes,
                result_instance=result.after,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _create_and_postcond_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        precond_constraints: Dict[str, List[str]],
        postcond_attr: str,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create postcondition branches with AND precondition constraints applied.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List["TreeNode"] = []

        postcond_cases = self._get_postcondition_branch_options(action, instance, postcond_attr)

        if not postcond_cases:
            return [
                self._create_compound_success_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_constraints=precond_constraints,
                    layer_state_cache=layer_state_cache,
                )
            ]

        for postcond_value, branch_type, effects in postcond_cases:
            modified_instance = instance.deep_copy()
            for attr_path, values in precond_constraints.items():
                if values:
                    AttributePath.parse(attr_path).set_value_in_instance(modified_instance, values[0])

            postcond_values = postcond_value if isinstance(postcond_value, list) else [postcond_value]
            AttributePath.parse(postcond_attr).set_value_in_instance(modified_instance, postcond_values[0])

            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = self._build_changes_list(result.changes)

            for attr_path, values in precond_constraints.items():
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                changes = narrowing + changes
            narrowing = compute_narrowing_change(parent_node.snapshot, postcond_attr, postcond_values)
            changes = narrowing + changes

            new_snapshot = capture_snapshot_with_values(
                result.after if result.after else modified_instance,
                postcond_attr,
                postcond_values,
                self.registry_manager,
                parent_node.snapshot,
            )

            # Normalize value and operator for consistent display
            if isinstance(postcond_value, list):
                if len(postcond_value) == 1:
                    # Single-item list: unwrap to string and use "equals"
                    display_value: Union[str, List[str]] = postcond_value[0]
                    operator = "equals"
                else:
                    # Multi-item list: keep as list and use "in"
                    display_value = postcond_value
                    operator = "in"
            else:
                display_value = postcond_value
                operator = "equals"

            branch_condition = BranchCondition(
                attribute=postcond_attr,
                operator=operator,
                value=display_value,
                source="postcondition",
                branch_type=branch_type,
            )

            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.OK.value,
                error=None,
                branch_condition=branch_condition,
                base_changes=changes,
                result_instance=result.after if result.after else modified_instance,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _set_attribute_value(self, instance: "ObjectInstance", attr_path: str, value: str) -> None:
        """Set an attribute to a single value."""
        AttributePath.parse(attr_path).set_value_in_instance(instance, value)

    def _update_snapshot_attribute(self, snapshot: "WorldSnapshot", attr_path: str, values: List[str]) -> None:
        """Update snapshot attribute, preserving existing value sets from trends."""
        attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
        if attr and not isinstance(attr.value, list):
            attr.value = values[0] if len(values) == 1 else values

    def _create_compound_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        parent_snapshot: Optional["WorldSnapshot"] = None,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> List["TreeNode"]:
        """
        Create branches for compound OR postcondition with multiple unknown attributes.

        For IF (C OR D) ELSE:
        - Success C: C satisfies, D unknown
        - Success D: D satisfies, C unknown
        - ELSE: C fails AND D fails (De Morgan)
        """
        from copy import deepcopy

        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect
        from simulator.core.tree.models import BranchCondition, NodeStatus
        from simulator.core.tree.node_factory import create_or_merge_node
        from simulator.core.tree.snapshot_utils import get_all_space_values, get_attribute_space_id
        from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List["TreeNode"] = []

        # Find the compound OR postcondition
        or_condition = None
        else_condition = None
        else_effects = []

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                if isinstance(effect.condition, OrCondition):
                    or_condition = effect.condition
                elif isinstance(effect.condition, AndCondition):
                    # This might be the ELSE branch (De Morgan of OR)
                    else_condition = effect.condition
                    else_effects = effect.then_effect

        if not or_condition:
            # No compound OR found, fall back to linear
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Create success branches for each disjunct in the OR
        for sub_cond in or_condition.conditions:
            if isinstance(sub_cond, AttributeCondition):
                attr_path = sub_cond.target.to_string()

                # Get satisfying values for this condition
                space_id = get_attribute_space_id(instance, attr_path)
                space_values = get_all_space_values(space_id, self.registry_manager)

                satisfying_values = []
                for v in space_values:
                    if evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager):
                        satisfying_values.append(v)

                if not satisfying_values:
                    continue

                # Create branch for this disjunct
                for val in satisfying_values:
                    new_instance = deepcopy(instance)
                    self._set_attribute_value(new_instance, attr_path, val)

                    # Apply action effects
                    from simulator.core.actions.action_applicator import ActionApplicator

                    result_instance, changes = ActionApplicator.apply(action, new_instance, parameters)

                    new_snapshot = self._capture_snapshot(result_instance, None)
                    new_snapshot, _ = self._snapshot_with_constrained_values(
                        new_snapshot, attr_path, [val], self.registry_manager
                    )

                    branch_condition = BranchCondition(
                        attribute=attr_path,
                        operator="equals",
                        value=val,
                        source="postcondition",
                        branch_type="if",
                    )

                    node = create_or_merge_node(
                        tree=tree,
                        parent_node=parent_node,
                        snapshot=new_snapshot,
                        action_name=action.name,
                        parameters=parameters,
                        status=NodeStatus.OK.value,
                        error=None,
                        branch_condition=branch_condition,
                        base_changes=changes,
                        result_instance=result_instance,
                        layer_state_cache=layer_state_cache,
                    )
                    branches.append(node)

        # Create ELSE branch (De Morgan: all conditions fail)
        if else_condition and else_effects:
            new_instance = deepcopy(instance)

            # Constrain all attributes to failing values
            all_fail_constraints = {}
            for sub_cond in or_condition.conditions:
                if isinstance(sub_cond, AttributeCondition):
                    attr_path = sub_cond.target.to_string()
                    space_id = get_attribute_space_id(instance, attr_path)
                    space_values = get_all_space_values(space_id, self.registry_manager)

                    fail_values = []
                    for v in space_values:
                        if not evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager):
                            fail_values.append(v)

                    if fail_values:
                        all_fail_constraints[attr_path] = fail_values
                        # Set first failing value
                        self._set_attribute_value(new_instance, attr_path, fail_values[0])

            # Apply action with else effects
            from simulator.core.actions.action_applicator import ActionApplicator

            result_instance, changes = ActionApplicator.apply(action, new_instance, parameters)

            new_snapshot = self._capture_snapshot(result_instance, None)

            # Apply all fail constraints to snapshot
            for attr_path, fail_vals in all_fail_constraints.items():
                new_snapshot, _ = self._snapshot_with_constrained_values(
                    new_snapshot, attr_path, fail_vals, self.registry_manager
                )

            # Create compound branch condition
            sub_conditions = []
            for attr_path, fail_vals in all_fail_constraints.items():
                op = "in" if len(fail_vals) > 1 else "equals"
                val = fail_vals if len(fail_vals) > 1 else fail_vals[0]
                sub_conditions.append(
                    BranchCondition(
                        attribute=attr_path,
                        operator=op,
                        value=val,
                        source="postcondition",
                        branch_type="else",
                    )
                )

            if len(sub_conditions) == 1:
                branch_condition = sub_conditions[0]
            else:
                first = sub_conditions[0]
                branch_condition = BranchCondition(
                    attribute=first.attribute,
                    operator=first.operator,
                    value=first.value,
                    source="postcondition",
                    branch_type="else",
                    compound_type="and",
                    sub_conditions=sub_conditions,
                )

            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.OK.value,
                error=None,
                branch_condition=branch_condition,
                base_changes=changes,
                result_instance=result_instance,
                layer_state_cache=layer_state_cache,
            )
            branches.append(node)

        return branches

    def _evaluate_condition_for_value(self, condition, value: str, instance: "ObjectInstance") -> bool:
        """Evaluate if a value satisfies a condition."""
        from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

        return evaluate_condition_for_value(condition, value, instance, self.registry_manager)

    def _capture_snapshot(self, instance: "ObjectInstance", parent_snapshot) -> "WorldSnapshot":
        """Capture snapshot from instance."""
        from simulator.core.tree.snapshot_utils import capture_snapshot

        return capture_snapshot(instance, self.registry_manager, parent_snapshot)

    def _snapshot_with_constrained_values(self, snapshot, attr_path, values, registry_manager):
        """Apply constraints to snapshot."""
        from simulator.core.tree.snapshot_utils import snapshot_with_constrained_values

        return snapshot_with_constrained_values(snapshot, attr_path, values, registry_manager)
