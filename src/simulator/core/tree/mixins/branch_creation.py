"""Branch creation mixin for TreeSimulationRunner.

Provides methods for creating success and fail branch nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from simulator.core.attributes import AttributePath
from simulator.core.tree.models import BranchCondition, NodeStatus
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import capture_snapshot_with_values, snapshot_with_constrained_values
from simulator.core.tree.utils.branch_condition_helpers import (
    create_compound_branch_condition,
    create_simple_branch_condition,
)

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree, TreeNode


class BranchCreationMixin:
    """Mixin providing branch node creation methods."""

    def _create_branch_success_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a success branch node (precondition passed)."""
        if layer_state_cache is None:
            layer_state_cache = {}

        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes

        new_snapshot = capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            self.registry_manager,
            parent_node.snapshot,
        )

        branch_condition = create_simple_branch_condition(attr_path, values, "precondition", "success")

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
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a fail branch node (precondition failed)."""
        if layer_state_cache is None:
            layer_state_cache = {}

        new_snapshot, constraint_changes = snapshot_with_constrained_values(
            parent_node.snapshot, attr_path, values, self.registry_manager
        )

        error_msg = self._build_precondition_error(action, attr_path, values)
        changes = compute_narrowing_change(parent_node.snapshot, attr_path, values)

        for cc in constraint_changes:
            changes.append(
                {
                    "attribute": cc["attribute"],
                    "before": cc["before"],
                    "after": cc["after"],
                    "kind": cc.get("kind", "constraint"),
                }
            )

        branch_condition = create_simple_branch_condition(attr_path, values, "precondition", "fail")

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
            result_instance=None,
            layer_state_cache=layer_state_cache,
        )

    def _create_compound_success_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_constraints: Dict[str, List[str]],
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a success node with multiple attribute constraints (for AND)."""
        if layer_state_cache is None:
            layer_state_cache = {}

        modified_instance = instance.deep_copy()
        for attr_path, values in attr_constraints.items():
            if values:
                AttributePath.parse(attr_path).set_value_in_instance(modified_instance, values[0])

        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        for attr_path, values in attr_constraints.items():
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes = narrowing + changes

        new_snapshot = capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            list(attr_constraints.keys())[0],
            list(attr_constraints.values())[0],
            self.registry_manager,
            parent_node.snapshot,
        )

        for attr_path, values in attr_constraints.items():
            attr = AttributePath.parse(attr_path).resolve_from_snapshot(new_snapshot)
            if attr:
                attr.value = values[0] if len(values) == 1 else values

        branch_condition = create_compound_branch_condition(attr_constraints, "precondition", "success", "and")

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

    def _create_compound_fail_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_constraints: Dict[str, List[str]],
        compound_type: str,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a fail node for compound condition using De Morgan.

        De Morgan's law:
        - NOT(A OR B) = NOT A AND NOT B → compound_type="and" (all fail together)
        - NOT(A AND B) = NOT A OR NOT B → separate fail nodes (this creates ONE of them)

        For OR preconditions, this creates a single compound AND fail node.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        new_snapshot = parent_node.snapshot
        changes: List[Dict[str, Any]] = []

        for attr_path, values in attr_constraints.items():
            new_snapshot, constraint_changes = snapshot_with_constrained_values(
                new_snapshot, attr_path, values, self.registry_manager
            )
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes.extend(narrowing)
            for cc in constraint_changes:
                changes.append(
                    {
                        "attribute": cc["attribute"],
                        "before": cc["before"],
                        "after": cc["after"],
                        "kind": cc.get("kind", "constraint"),
                    }
                )

        constraint_strs = []
        for attr_path, values in attr_constraints.items():
            val_str = values[0] if len(values) == 1 else "{" + ", ".join(values) + "}"
            constraint_strs.append(f"{attr_path}={val_str}")
        error_msg = f"Precondition failed: {' AND '.join(constraint_strs)}"

        # De Morgan: OR precondition creates AND fail branch
        demorgan_type = "and" if compound_type == "or" and len(attr_constraints) > 1 else None

        # Build compound fail condition using helper
        sub_conditions: List[BranchCondition] = []
        for attr_path, values in attr_constraints.items():
            sub_conditions.append(create_simple_branch_condition(attr_path, values, "precondition", "fail"))

        first_attr = list(attr_constraints.keys())[0]
        first_values = list(attr_constraints.values())[0]

        branch_condition = BranchCondition(
            attribute=first_attr,
            operator="in" if len(first_values) > 1 else "equals",
            value=first_values if len(first_values) > 1 else first_values[0],
            source="precondition",
            branch_type="fail",
            compound_type=demorgan_type,
            sub_conditions=sub_conditions if len(sub_conditions) > 1 else None,
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
            result_instance=None,
            layer_state_cache=layer_state_cache,
        )

    def _create_branch_case_node(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: "TreeNode",
        action: "Action",
        parameters: Dict[str, str],
        attr_path: str,
        value: Union[str, List[str]],
        branch_type: str,
        effects: Any,
        layer_state_cache: Optional[Dict[str, Tuple["TreeNode", "ObjectInstance"]]] = None,
    ) -> "TreeNode":
        """Create a branch node for a postcondition case (if/elif/else)."""
        if layer_state_cache is None:
            layer_state_cache = {}

        values = value if isinstance(value, list) else [value]
        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes

        new_snapshot = capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            self.registry_manager,
            parent_node.snapshot,
        )

        branch_condition = create_simple_branch_condition(attr_path, value, "postcondition", branch_type)

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

    def _clone_instance_with_values(
        self, instance: "ObjectInstance", attr_path: str, values: List[str]
    ) -> "ObjectInstance":
        """Clone an instance and constrain an attribute to specific value(s)."""
        new_instance = instance.deep_copy()
        if values:
            # Set all values, not just the first one
            value_to_set = values[0] if len(values) == 1 else values
            AttributePath.parse(attr_path).set_value_in_instance(new_instance, value_to_set)
        return new_instance
