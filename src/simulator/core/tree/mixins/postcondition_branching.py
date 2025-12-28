"""
Mixin for postcondition analysis and branching.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from simulator.core.tree.models import NodeStatus, TreeNode, WorldSnapshot
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import capture_snapshot
from simulator.core.tree.utils.change_helpers import build_changes_list
from simulator.core.tree.utils.condition_evaluation import (
    evaluate_condition_for_value,
    get_possible_values_for_attribute,
    get_satisfying_values_for_and_condition,
)
from simulator.core.tree.utils.instance_helpers import (
    clone_instance_with_multi_values,
    update_snapshot_attribute,
)

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.actions.conditions.base import Condition
    from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree


class PostconditionBranchingMixin:
    """Mixin providing methods for postcondition analysis and branching."""

    def _get_unknown_postcondition_attribute(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Optional[str]:
        """
        Get the unknown attribute in postcondition that would cause branching.

        An attribute is considered "unknown" (requiring branching) if:
        - Its current_value is "unknown"
        - It's a value SET (list) in the parent snapshot (e.g., from a trend)

        Returns:
            Attribute path if unknown/multi-valued, None if all known single values
        """
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                unknown = self._find_unknown_in_condition(effect.condition, instance, parent_snapshot)
                if unknown:
                    return unknown
        return None

    def _has_compound_postcondition(
        self, action: "Action", instance: "ObjectInstance", parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Optional[Tuple["Condition", List[Any], List[Tuple[str, "AttributeCondition"]]]]:
        """
        Check if the action has a compound condition (AND/OR) in postcondition with unknowns.

        Returns (condition, effects, unknowns) if compound with unknowns, None otherwise.
        """
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                cond = effect.condition
                if isinstance(cond, (AndCondition, OrCondition)):
                    # Check if any sub-condition has unknowns
                    unknowns = self._get_unknown_attributes_in_condition(cond, instance, parent_snapshot)
                    if unknowns:
                        then_eff = effect.then_effect
                        then_effects = then_eff if isinstance(then_eff, list) else [then_eff]
                        return (cond, then_effects, unknowns)
        return None

    def _get_postcondition_branch_options(
        self, action: "Action", instance: "ObjectInstance", attribute_path: str
    ) -> List[Tuple[Union[str, List[str]], str, List[Any]]]:
        """
        Get all possible branch options for a postcondition attribute.

        Returns list of (value, branch_type, effects) tuples.
        The value can be a single string or a list of strings (for else branch).

        Example for flat if-elif structure on battery.level == full / high / medium / low:
            [("full", "if", [...effects...]),
             ("high", "elif", [...effects...]),
             ("medium", "elif", [...effects...]),
             ("low", "elif", [...effects...])]

        If there are remaining values not covered, adds else branch.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        options: List[Tuple[Union[str, List[str]], str, List[Any]]] = []
        used_values: set = set()

        # Get all possible values from the attribute's space
        all_values: List[str] = []
        try:
            # Parse attribute path to get part and attribute
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

        # Extract ALL conditional effects that check this attribute (flat if-elif-else)
        conditional_index = 0
        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                cond = effect.condition
                if isinstance(cond, AttributeCondition) and cond.target.to_string() == attribute_path:
                    # First matching conditional is "if", rest are "elif"
                    branch_type = "if" if conditional_index == 0 else "elif"
                    conditional_index += 1

                    # Convert then_effect to list if needed
                    then_effects = effect.then_effect if isinstance(effect.then_effect, list) else [effect.then_effect]

                    if cond.operator == "equals":
                        value = cond.value
                        options.append((value, branch_type, then_effects))
                        used_values.add(value)
                    elif cond.operator == "in" and isinstance(cond.value, list):
                        # "in" operator with list of values - treat as grouped else branch
                        value = cond.value  # Keep as list for value set display
                        options.append((value, branch_type, then_effects))
                        used_values.update(cond.value)
                    elif cond.operator in ("gte", "lte", "gt", "lt"):
                        # Comparison operators - expand to value list from space
                        try:
                            ai = cond.target.resolve(instance)
                            space = self.registry_manager.spaces.get(ai.spec.space_id)
                            if space:
                                satisfying = space.get_values_for_comparison(str(cond.value), cond.operator)
                                if satisfying:
                                    options.append((satisfying, branch_type, then_effects))
                                    used_values.update(satisfying)
                        except (ValueError, AttributeError):
                            pass

        # Add else branch with remaining values (if any values not covered)
        if all_values and used_values:
            remaining = [v for v in all_values if v not in used_values]
            if remaining:
                # No explicit else effects in flat structure - just empty effects
                options.append((remaining, "else", []))

        return options

    def _create_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        parent_snapshot: Optional[WorldSnapshot] = None,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """
        Create N+1 branches for postcondition: one for each if/elif case + else.

        When postcondition has if-elif-else structure checking an unknown attribute:
        - Each if/elif case gets its own branch with that specific value
        - The else branch gets remaining values as a set

        If parent_snapshot has a value SET for attr_path, we constrain branches
        to only those values.

        Uses layer_state_cache for DAG deduplication.

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            attr_path: Path to the unknown attribute
            parent_snapshot: Optional parent snapshot (for constraining value sets)
            layer_state_cache: Optional cache for deduplication

        Returns:
            List of N+1 TreeNodes
        """
        if layer_state_cache is None:
            layer_state_cache = {}
        # Get all branch options from action structure
        options = self._get_postcondition_branch_options(action, instance, attr_path)

        if not options:
            # No conditional effects, use linear execution
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Get constrained values from parent snapshot (if value set exists)
        constrained_values: Optional[List[str]] = None
        if parent_snapshot:
            snapshot_value = parent_snapshot.get_attribute_value(attr_path)
            if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                constrained_values = list(snapshot_value)

        branches: List[TreeNode] = []
        used_values: set = set()

        for value, branch_type, effects in options:
            # Filter by constrained values if available
            if constrained_values is not None:
                if isinstance(value, list):
                    # Else branch: intersect with constrained values
                    filtered_value = [v for v in value if v in constrained_values]
                    if not filtered_value:
                        continue
                    value = filtered_value if len(filtered_value) > 1 else filtered_value[0]
                else:
                    # Single value: check if in constrained values
                    if value not in constrained_values:
                        continue

            # Track used values for else branch calculation
            if isinstance(value, list):
                used_values.update(value)
            else:
                used_values.add(value)

            # Create a branch node for this case
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
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        precond_pass_values: List[str],
        postcond_attr: str,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """
        Create N branches for postcondition, constrained by precondition pass values.

        If same attribute: intersect postcondition cases with pass values.
        If different attribute: each postcondition branch has full pass values for precond_attr.

        Uses layer_state_cache for DAG deduplication.

        Returns:
            List of N TreeNodes for success branches
        """
        if layer_state_cache is None:
            layer_state_cache = {}
        # Get postcondition cases from action structure
        postcond_cases = self._get_postcondition_branch_options(action, instance, postcond_attr)

        if not postcond_cases:
            # No conditional structure - single success branch
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
        branches: List[TreeNode] = []
        used_postcond_values: set = set()

        for case_value, branch_type, effects in postcond_cases:
            # Determine values for this branch
            if same_attribute:
                # Intersect with precondition pass values
                if isinstance(case_value, list):
                    # For else branch, intersect with pass values
                    branch_values = [v for v in case_value if v in precond_pass_values]
                    # The constrained postcond_value is the intersection
                    constrained_postcond_value = (
                        branch_values if len(branch_values) > 1 else (branch_values[0] if branch_values else None)
                    )
                else:
                    branch_values = [case_value] if case_value in precond_pass_values else []
                    constrained_postcond_value = case_value if branch_values else None

                if not branch_values:
                    continue  # This case doesn't overlap with pass values
            else:
                # Different attribute - full pass values for precond_attr
                branch_values = precond_pass_values
                constrained_postcond_value = case_value

            # Track used postcond values for same-attribute else calculation
            if same_attribute:
                if isinstance(case_value, list):
                    used_postcond_values.update(case_value)
                else:
                    used_postcond_values.add(case_value)

            # Create the branch node with effects applied
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

    def _create_compound_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "Condition",
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
        precond_attr_values: Optional[Dict[str, List[str]]] = None,
    ) -> List[TreeNode]:
        """
        Create branches for compound (AND/OR) conditions in postconditions.

        For AND condition in postcondition:
        - THEN branch: All attributes constrained to satisfying values (single branch)
        - ELSE branch: De Morgan → NOT(A AND B) = NOT(A) OR NOT(B) → Multiple branches

        For OR condition in postcondition:
        - THEN branches: One per satisfied disjunct (multiple branches)
        - ELSE branch: De Morgan → NOT(A OR B) = NOT(A) AND NOT(B) → Single branch

        Args:
            tree: Simulation tree
            instance: Object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            condition: The compound condition (AndCondition or OrCondition)
            effects: Effects to apply when condition is true
            unknowns: List of (attr_path, sub_condition) for unknown attributes
            layer_state_cache: DAG deduplication cache
            precond_attr_values: Optional dict of precondition constraints to include in branch conditions

        Returns:
            List of branch nodes
        """
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List[TreeNode] = []

        if isinstance(condition, AndCondition):
            branches = self._create_and_postcondition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                effects=effects,
                unknowns=unknowns,
                layer_state_cache=layer_state_cache,
            )
        elif isinstance(condition, OrCondition):
            branches = self._create_or_postcondition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                effects=effects,
                unknowns=unknowns,
                layer_state_cache=layer_state_cache,
            )
        else:
            # Fallback to linear
            branches = self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        return branches

    def _create_and_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "AndCondition",
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """
        Create branches for AND condition in postcondition.

        THEN: Single branch with all attributes constrained to satisfying values
        ELSE: De Morgan → NOT(A AND B) = NOT(A) OR NOT(B) → Multiple branches
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List[TreeNode] = []

        # Get satisfying values for AND (all must be satisfied)
        satisfying = get_satisfying_values_for_and_condition(
            condition, instance, parent_node.snapshot, self.registry_manager
        )

        # THEN branch: all attributes constrained to satisfying values
        if satisfying and all(v for v in satisfying.values()):
            # Clone instance with all constrained values
            modified_instance = clone_instance_with_multi_values(instance, satisfying)

            # Apply action effects
            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = build_changes_list(result.changes)

            # Add narrowing changes
            for attr_path, values in satisfying.items():
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                changes = narrowing + changes

            result_instance = result.after if result.after else modified_instance
            new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

            # Create branch condition
            branch_condition = self._create_compound_branch_condition(
                attr_values=satisfying,
                source="postcondition",
                branch_type="if",
                compound_type="and",
            )

            then_node = create_or_merge_node(
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
            branches.append(then_node)

        # ELSE branches: De Morgan → NOT(A AND B) = NOT(A) OR NOT(B)
        # Create one fail branch per attribute (where that attribute fails)
        for attr_path, sub_cond in unknowns:
            possible_values, _ = get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None, self.registry_manager
            )
            if not possible_values:
                continue

            # Get satisfying values for this sub-condition
            satisfying_for_attr = [
                v for v in possible_values if evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager)
            ]

            # Complement = values that FAIL this condition
            complement = [v for v in possible_values if v not in satisfying_for_attr]

            if not complement:
                continue  # This condition can't fail

            # Apply action WITHOUT the conditional effects (else path)
            modified_instance = clone_instance_with_multi_values(instance, {attr_path: complement})
            result = self.engine.apply_action(modified_instance, action, parameters)

            # Get attributes actually modified by EFFECTS (before adding narrowing)
            effect_changes = build_changes_list(result.changes)
            effect_changed_attrs = {c.get("attribute") for c in effect_changes if c.get("kind") == "value"}

            # Build combined changes with narrowing
            changes = list(effect_changes)
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, complement)
            changes = narrowing + changes

            result_instance = result.after if result.after else modified_instance
            new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

            # Only update snapshot if this attr was NOT modified by effects
            if attr_path not in effect_changed_attrs:
                update_snapshot_attribute(new_snapshot, attr_path, complement)

            # Create branch condition for else
            branch_condition = self._create_simple_branch_condition(attr_path, complement, "postcondition", "else")

            else_node = create_or_merge_node(
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
            branches.append(else_node)

        return branches

    def _create_or_postcondition_branches(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        condition: "OrCondition",
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """
        Create branches for OR condition in postcondition.

        THEN: Multiple branches, one per satisfied disjunct
        ELSE: De Morgan → NOT(A OR B) = NOT(A) AND NOT(B) → Single branch
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        branches: List[TreeNode] = []

        # THEN branches: one per disjunct that can be satisfied
        for attr_path, sub_cond in unknowns:
            possible_values, _ = get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None, self.registry_manager
            )
            if not possible_values:
                continue

            # Get satisfying values for this sub-condition
            satisfying = [
                v for v in possible_values if evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager)
            ]

            if not satisfying:
                continue

            # Apply action WITH effects (this disjunct is true)
            modified_instance = clone_instance_with_multi_values(instance, {attr_path: satisfying})
            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = build_changes_list(result.changes)

            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, satisfying)
            changes = narrowing + changes

            result_instance = result.after if result.after else modified_instance
            new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

            # Create branch condition
            branch_condition = self._create_simple_branch_condition(attr_path, satisfying, "postcondition", "if")

            then_node = create_or_merge_node(
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
            branches.append(then_node)

        # ELSE branch: De Morgan → properly nested structure
        # Use recursive De Morgan to preserve nested condition structure
        parent_snapshot = parent_node.snapshot if parent_node else None
        branch_condition = self._create_demorgan_branch_condition(
            condition, instance, parent_snapshot, "postcondition", "else"
        )

        if branch_condition is not None:
            # Collect complement values for snapshot update (flattened)
            complement_values: Dict[str, List[str]] = {}
            for attr_path, sub_cond in unknowns:
                possible_values, _ = get_possible_values_for_attribute(
                    attr_path, instance, parent_snapshot, self.registry_manager
                )
                if not possible_values:
                    continue

                satisfying = [
                    v
                    for v in possible_values
                    if evaluate_condition_for_value(sub_cond, v, instance, self.registry_manager)
                ]
                complement = [v for v in possible_values if v not in satisfying]

                if complement:
                    complement_values[attr_path] = complement

            if complement_values:
                # All attributes are constrained to their complements
                modified_instance = clone_instance_with_multi_values(instance, complement_values)
                result = self.engine.apply_action(modified_instance, action, parameters)

                # Get attributes actually modified by EFFECTS
                effect_changes = build_changes_list(result.changes)
                effect_changed_attrs = {c.get("attribute") for c in effect_changes if c.get("kind") == "value"}

                # Build combined changes with narrowing
                changes = list(effect_changes)
                for attr_path, values in complement_values.items():
                    narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                    changes = narrowing + changes

                result_instance = result.after if result.after else modified_instance
                new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

                # Only update snapshot for constraint attrs NOT modified by effects
                for attr_path, values in complement_values.items():
                    if attr_path not in effect_changed_attrs:
                        update_snapshot_attribute(new_snapshot, attr_path, values)

                else_node = create_or_merge_node(
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
                branches.append(else_node)

        return branches
