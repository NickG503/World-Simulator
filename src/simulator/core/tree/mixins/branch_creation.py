"""
Mixin for creating branch nodes in the simulation tree.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union

from simulator.core.tree.models import BranchCondition, NodeStatus, TreeNode
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import (
    capture_snapshot,
    capture_snapshot_with_values,
    snapshot_with_constrained_values,
)
from simulator.core.tree.utils.change_helpers import build_changes_list, build_precondition_error
from simulator.core.tree.utils.instance_helpers import (
    clone_instance_with_multi_values,
    clone_instance_with_values,
    set_attribute_value,
    update_snapshot_attribute,
)

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree


class BranchCreationMixin:
    """Mixin providing methods for creating branch nodes."""

    def _create_branch_success_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a success branch node (precondition passed).

        Uses layer_state_cache for DAG deduplication.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with the constrained values
        modified_instance = clone_instance_with_values(instance, attr_path, values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = build_changes_list(result.changes)

        # Add narrowing change if the value actually narrowed
        narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes  # Put narrowing first

        # Capture the new state (pass parent snapshot for trend-based value set computation)
        new_snapshot = capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            self.registry_manager,
            parent_node.snapshot,
        )

        # Determine operator based on value count
        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]

        branch_condition = BranchCondition(
            attribute=attr_path,
            operator=operator,
            value=value,
            source="precondition",
            branch_type="success",
        )

        return create_or_merge_node(
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

    def _create_branch_fail_node(
        self,
        tree: "SimulationTree",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a fail branch node (precondition failed).

        Uses layer_state_cache for DAG deduplication.
        Also enforces constraints (e.g., if battery=empty, bulb turns off).
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Capture snapshot with constrained values and enforce constraints
        new_snapshot, constraint_changes = snapshot_with_constrained_values(
            parent_node.snapshot, attr_path, values, self.registry_manager
        )

        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]

        # Build detailed error message matching the engine's format
        error_msg = build_precondition_error(action, attr_path, values)

        # Include the narrowing as a change if the value actually changed
        changes = compute_narrowing_change(parent_node.snapshot, attr_path, values)

        # Add constraint-induced changes (already in before/after format)
        for cc in constraint_changes:
            changes.append(
                {
                    "attribute": cc["attribute"],
                    "before": cc["before"],
                    "after": cc["after"],
                    "kind": cc.get("kind", "constraint"),
                }
            )

        branch_condition = BranchCondition(
            attribute=attr_path,
            operator=operator,
            value=value,
            source="precondition",
            branch_type="fail",
        )

        return create_or_merge_node(
            tree=tree,
            parent_node=parent_node,
            snapshot=new_snapshot,
            action_name=action.name,
            parameters=parameters,
            status=NodeStatus.REJECTED.value,
            error=error_msg,
            branch_condition=branch_condition,
            base_changes=changes,
            result_instance=None,  # No changes made for failed nodes
            layer_state_cache=layer_state_cache,
        )

    def _create_branch_case_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        value: Union[str, List[str]],
        branch_type: str,
        effects: Any,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a branch node for a postcondition case (if/elif/else).

        Uses layer_state_cache for DAG deduplication.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with the specific value(s)
        values = value if isinstance(value, list) else [value]
        modified_instance = clone_instance_with_values(instance, attr_path, values)

        # Apply the action
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = build_changes_list(result.changes)

        # Add narrowing change if the value actually narrowed
        narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes  # Put narrowing first

        # Capture new state (pass parent snapshot for trend-based value set computation)
        new_snapshot = capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            self.registry_manager,
            parent_node.snapshot,
        )

        operator = "in" if isinstance(value, list) else "equals"

        branch_condition = BranchCondition(
            attribute=attr_path,
            operator=operator,
            value=value,
            source="postcondition",
            branch_type=branch_type,
        )

        return create_or_merge_node(
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

    def _create_postcond_case_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        precond_attr: str,
        precond_values: List[str],
        postcond_attr: str,
        postcond_value: Union[str, List[str]],
        branch_type: str,
        effects: List[Any],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a node for a postcondition case with effects applied.

        Uses layer_state_cache for DAG deduplication.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        from copy import deepcopy

        # Clone instance and set the first pass value for action application
        new_instance = deepcopy(instance)

        # For action application, set to first value (action needs single value)
        if precond_attr == postcond_attr:
            # Same attribute - use the constrained values from intersection
            if isinstance(postcond_value, list):
                set_attribute_value(new_instance, precond_attr, postcond_value[0])
            else:
                set_attribute_value(new_instance, precond_attr, postcond_value)
        else:
            # Different attributes - set precond attr to first pass value
            set_attribute_value(new_instance, precond_attr, precond_values[0])
            if isinstance(postcond_value, list):
                set_attribute_value(new_instance, postcond_attr, postcond_value[0])
            else:
                set_attribute_value(new_instance, postcond_attr, postcond_value)

        # Apply effects for this branch using the engine
        action_result = self.engine.apply_action(new_instance, action, parameters)
        raw_changes = action_result.changes if action_result else []

        # Build changes list from raw changes
        changes = build_changes_list(raw_changes)

        # Add narrowing changes for the constrained attributes
        # For precond_attr: narrowed from parent's value to precond_values
        narrowing = compute_narrowing_change(parent_node.snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            # Also add narrowing for postcond_attr if different
            postcond_vals = postcond_value if isinstance(postcond_value, list) else [postcond_value]
            narrowing.extend(compute_narrowing_change(parent_node.snapshot, postcond_attr, postcond_vals))
        changes = narrowing + changes  # Put narrowing first

        # Use the resulting instance after effects are applied
        result_instance = action_result.after if action_result and action_result.after else new_instance

        # Capture snapshot then update with constrained values
        snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        # Update the snapshot with the constrained value set for this branch
        update_snapshot_attribute(snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            if isinstance(postcond_value, list):
                update_snapshot_attribute(snapshot, postcond_attr, postcond_value)
            else:
                update_snapshot_attribute(snapshot, postcond_attr, [postcond_value])

        # Display value for branch condition
        postcond_display = postcond_value

        # Create branch condition
        branch_condition = BranchCondition(
            attribute=postcond_attr,
            operator="equals",
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

    def _create_and_success_branch(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_values: Dict[str, List[str]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a success branch for AND condition with multiple constrained attributes."""
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with all constrained values
        modified_instance = clone_instance_with_multi_values(instance, attr_values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = build_changes_list(result.changes)

        # Add narrowing changes for all constrained attributes
        for attr_path, values in attr_values.items():
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes = narrowing + changes

        # Capture new state with all constrained values
        result_instance = result.after if result.after else modified_instance
        new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        # Update snapshot with constrained value sets
        for attr_path, values in attr_values.items():
            update_snapshot_attribute(new_snapshot, attr_path, values)

        # Create compound branch condition
        branch_condition = self._create_compound_branch_condition(
            attr_values=attr_values,
            source="precondition",
            branch_type="success",
            compound_type="and",
        )

        return create_or_merge_node(
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

    def _create_and_postcond_branch(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        attr_values: Dict[str, List[str]],
        postcond_attr: str,
        postcond_values: List[str],
        branch_type: str,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> TreeNode:
        """Create a branch for AND precondition with postcondition constraint.

        Combines precondition AND constraints with postcondition if/elif/else case.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with all constrained values
        modified_instance = clone_instance_with_multi_values(instance, attr_values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = build_changes_list(result.changes)

        # Add narrowing changes for all constrained attributes
        for attr_path, values in attr_values.items():
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes = narrowing + changes

        # Capture new state with all constrained values
        result_instance = result.after if result.after else modified_instance
        new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        # Update snapshot with constrained value sets
        for attr_path, values in attr_values.items():
            update_snapshot_attribute(new_snapshot, attr_path, values)

        # Create branch condition showing postcondition path
        operator = "in" if len(postcond_values) > 1 else "equals"
        value = postcond_values if len(postcond_values) > 1 else postcond_values[0]

        branch_condition = BranchCondition(
            attribute=postcond_attr,
            operator=operator,
            value=value,
            source="postcondition",
            branch_type=branch_type,
        )

        return create_or_merge_node(
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

    def _create_compound_branch_condition(
        self,
        attr_values: Dict[str, List[str]],
        source: str,
        branch_type: str,
        compound_type: str = "and",
    ) -> BranchCondition:
        """Create a compound BranchCondition for multiple attributes.

        Args:
            attr_values: Dict mapping attr_path -> list of constrained values
            source: "precondition" or "postcondition"
            branch_type: "success", "fail", "if", etc.
            compound_type: "and" or "or"

        Returns:
            BranchCondition with sub_conditions for each attribute
        """
        sub_conditions = []
        for attr_path, values in attr_values.items():
            operator = "in" if len(values) > 1 else "equals"
            value = values if len(values) > 1 else values[0]
            sub_conditions.append(
                BranchCondition(
                    attribute=attr_path,
                    operator=operator,
                    value=value,
                    source=source,
                    branch_type=branch_type,
                )
            )

        # If only one attribute, return simple condition
        if len(sub_conditions) == 1:
            return sub_conditions[0]

        # Return compound condition
        return BranchCondition(
            attribute="",  # Not used for compound
            operator="",  # Not used for compound
            value="",  # Not used for compound
            source=source,
            branch_type=branch_type,
            compound_type=compound_type,
            sub_conditions=sub_conditions,
        )

    def _create_simple_branch_condition(
        self,
        attr_path: str,
        values: List[str],
        source: Literal["precondition", "postcondition"],
        branch_type: Literal["if", "elif", "else", "success", "fail"],
    ) -> BranchCondition:
        """Create a simple branch condition for a single attribute."""
        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]
        return BranchCondition(
            attribute=attr_path,
            operator=operator,
            value=value,
            source=source,
            branch_type=branch_type,
        )

    def _extract_postcondition_branch(self, action: "Action", instance: "ObjectInstance") -> Optional[BranchCondition]:
        """
        Extract branch condition from conditional effects.

        Identifies which branch was taken based on current values.
        """
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                cond = effect.condition
                if isinstance(cond, AttributeCondition):
                    try:
                        ai = cond.target.resolve(instance)
                        actual_value = ai.current_value

                        return BranchCondition(
                            attribute=cond.target.to_string(),
                            operator=cond.operator,
                            value=str(actual_value) if actual_value else "unknown",
                            source="postcondition",
                        )
                    except Exception:
                        pass

        return None

    def _extract_precondition_failure(
        self, action: "Action", instance: "ObjectInstance", reason: Optional[str]
    ) -> Optional[BranchCondition]:
        """Extract branch condition from precondition failure."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                try:
                    ai = condition.target.resolve(instance)
                    actual_value = ai.current_value

                    return BranchCondition(
                        attribute=condition.target.to_string(),
                        operator=condition.operator,
                        value=str(actual_value) if actual_value else "unknown",
                        source="precondition",
                        branch_type="fail",
                    )
                except Exception:
                    pass

        return None
