"""Branch creation mixin for TreeSimulationRunner.

Provides methods for creating success and fail branch nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from simulator.core.attributes import AttributePath
from simulator.core.tree.models import BranchCondition, NodeStatus
from simulator.core.tree.node_factory import compute_narrowing_change, create_or_merge_node
from simulator.core.tree.snapshot_utils import capture_snapshot_with_values, snapshot_with_constrained_values

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

        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]

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

        first_attr = list(attr_constraints.keys())[0]
        first_values = attr_constraints[first_attr]
        operator = "in" if len(first_values) > 1 else "equals"
        value = first_values if len(first_values) > 1 else first_values[0]

        branch_condition = BranchCondition(
            attribute=first_attr,
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
        """Create a fail node for compound condition using De Morgan."""
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

        first_attr = list(attr_constraints.keys())[0]
        first_values = list(attr_constraints.values())[0]
        branch_condition = BranchCondition(
            attribute=first_attr,
            operator="in" if len(first_values) > 1 else "equals",
            value=first_values if len(first_values) > 1 else first_values[0],
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

    def _clone_instance_with_values(
        self, instance: "ObjectInstance", attr_path: str, values: List[str]
    ) -> "ObjectInstance":
        """Clone an instance and constrain an attribute to specific value(s)."""
        new_instance = instance.deep_copy()
        if values:
            AttributePath.parse(attr_path).set_value_in_instance(new_instance, values[0])
        return new_instance
