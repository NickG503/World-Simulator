"""
Mixin for core action processing logic.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from simulator.core.tree.models import NodeStatus, TreeNode
from simulator.core.tree.node_factory import create_error_node, create_or_merge_node
from simulator.core.tree.snapshot_utils import capture_snapshot
from simulator.core.tree.utils.change_helpers import build_changes_list

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.tree.models import SimulationTree


@dataclass
class ActionResult:
    """Result of processing an action."""

    node: TreeNode
    instance: Optional["ObjectInstance"] = None
    action: Optional["Action"] = None


class ActionProcessingMixin:
    """Mixin providing core action processing methods."""

    def _process_action_multi(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[ActionResult]:
        """Process action and return results for all branches, with DAG deduplication."""
        if layer_state_cache is None:
            layer_state_cache = {}

        result = self._process_action(
            tree=tree,
            instance=instance,
            parent_node=parent_node,
            action_name=action_name,
            parameters=parameters,
            verbose=verbose,
            layer_state_cache=layer_state_cache,
        )

        # Check if multiple children were created (branching occurred)
        parent_children = tree.nodes[parent_node.id].children_ids
        if len(parent_children) > 1:
            # Return results for ALL branches
            results = []
            for child_id in parent_children:
                child_node = tree.nodes[child_id]
                # First, constrain the instance with the branch_condition values
                bc = child_node.branch_condition
                if bc and bc.attribute:
                    from simulator.core.tree.utils.instance_helpers import clone_instance_with_values

                    values = bc.value if isinstance(bc.value, list) else [bc.value]
                    constrained_instance = clone_instance_with_values(instance, bc.attribute, values)
                else:
                    constrained_instance = instance.deep_copy()

                if child_node.action_status == NodeStatus.OK.value:
                    # Apply action to the CONSTRAINED instance for success branch
                    engine_result = self.engine.apply_action(constrained_instance, result.action, parameters)
                    child_instance = engine_result.after if engine_result.after else constrained_instance
                else:
                    # For failed branches, keep the constrained instance (action wasn't applied)
                    child_instance = constrained_instance
                results.append(ActionResult(node=child_node, instance=child_instance, action=result.action))
            return results

        # Single branch - return as list
        return [result]

    def _process_action(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> ActionResult:
        """Process action, creating branches for unknown attributes."""
        import logging

        logger = logging.getLogger(__name__)

        if layer_state_cache is None:
            layer_state_cache = {}
        # Resolve action
        action = self.registry_manager.create_behavior_enhanced_action(instance.type.name, action_name)

        if not action:
            # Action not found - create error node
            error_snapshot = capture_snapshot(instance, self.registry_manager, parent_node.snapshot)
            node = create_error_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=error_snapshot,
                action_name=action_name,
                parameters=parameters,
                error=f"Action '{action_name}' not found for {instance.type.name}",
            )
            tree.add_node(node)
            return ActionResult(node=node, instance=None, action=None)

        # Check for unknown attributes that would cause branching
        # Pass parent snapshot to detect value sets from trends
        parent_snapshot = parent_node.snapshot if parent_node else None
        precond_unknown = self._get_unknown_precondition_attribute(action, instance, parent_snapshot)
        postcond_unknown = self._get_unknown_postcondition_attribute(action, instance, parent_snapshot)
        postcond_compound = self._has_compound_postcondition(action, instance, parent_snapshot)

        if verbose:
            if precond_unknown or postcond_unknown or postcond_compound:
                logger.info(
                    "Branch points detected - precondition: %s, postcondition: %s, compound: %s",
                    precond_unknown,
                    postcond_unknown,
                    postcond_compound is not None,
                )

        # Determine which branching mode to use
        child_nodes: List[TreeNode] = []

        if precond_unknown:
            # Combined branching: precondition pass/fail + postcondition if/elif/else
            # This handles both same-attribute and different-attribute cases
            child_nodes = self._create_combined_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                precond_attr=precond_unknown,
                postcond_attr=postcond_unknown,  # May be None or same as precond_attr
                layer_state_cache=layer_state_cache,
            )
            if verbose:
                logger.info("Created %d combined branches", len(child_nodes))
        else:
            # No precondition branching - check precondition result first
            precond_result = self.engine.apply_action(instance, action, parameters)

            if precond_result.status == "rejected":
                # Precondition failed with known values - single rejected node
                child_nodes = self._apply_action_linear(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    layer_state_cache=layer_state_cache,
                )
            elif postcond_compound:
                # Compound condition in postcondition - special handling
                compound_cond, compound_effects, compound_unknowns = postcond_compound
                child_nodes = self._create_compound_postcondition_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    condition=compound_cond,
                    effects=compound_effects,
                    unknowns=compound_unknowns,
                    layer_state_cache=layer_state_cache,
                )
                if verbose:
                    logger.info("Created %d compound postcondition branches", len(child_nodes))
            elif postcond_unknown:
                # Branch on postcondition: one branch per if/elif + else
                # Pass parent_snapshot to constrain values to value set if present
                child_nodes = self._create_postcondition_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_path=postcond_unknown,
                    parent_snapshot=parent_snapshot,
                    layer_state_cache=layer_state_cache,
                )
                if verbose:
                    logger.info("Created %d postcondition branches", len(child_nodes))
            else:
                # Linear execution (all values known)
                child_nodes = self._apply_action_linear(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    layer_state_cache=layer_state_cache,
                )

        # Add the node(s) to tree
        if child_nodes:
            # For multiple branches, use add_branch_nodes
            if len(child_nodes) > 1:
                tree.add_branch_nodes(parent_node.id, child_nodes)
            else:
                for node in child_nodes:
                    tree.add_node(node)

            # Return first node and update instance if succeeded
            primary_node = child_nodes[0]
            new_instance = None

            if primary_node.action_status == NodeStatus.OK.value:
                # Apply action to get the updated instance
                result = self.engine.apply_action(instance, action, parameters)
                if result.after:
                    new_instance = result.after

            return ActionResult(node=primary_node, instance=new_instance, action=action)

        # Should not happen, but handle gracefully
        error_snapshot = capture_snapshot(instance, self.registry_manager, parent_node.snapshot)
        error_node = create_error_node(
            tree=tree,
            parent_node=parent_node,
            snapshot=error_snapshot,
            action_name=action_name,
            parameters=parameters,
            error="No nodes created from action",
        )
        tree.add_node(error_node)
        return ActionResult(node=error_node, instance=None, action=None)

    def _apply_action_linear(
        self,
        tree: "SimulationTree",
        instance: "ObjectInstance",
        parent_node: TreeNode,
        action: "Action",
        parameters: Dict[str, str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, "ObjectInstance"]]] = None,
    ) -> List[TreeNode]:
        """Apply action linearly (no branching), returning single node.

        Returns:
            List containing single TreeNode (may be existing node if deduplicated)
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        result = self.engine.apply_action(instance, action, parameters)

        # Build changes list
        changes = build_changes_list(result.changes)

        if result.status == "ok":
            # Success - capture new state (preserve value sets from parent)
            if result.after:
                new_snapshot = capture_snapshot(result.after, self.registry_manager, parent_node.snapshot)
            else:
                new_snapshot = parent_node.snapshot
            branch_condition = self._extract_postcondition_branch(action, instance)
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
                result_instance=result.after if result.after else instance,
                layer_state_cache=layer_state_cache,
            )
            return [node]

        elif result.status == "rejected":
            # Precondition failed - snapshot unchanged
            branch_condition = self._extract_precondition_failure(action, instance, result.reason)
            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=parent_node.snapshot,
                action_name=action.name,
                parameters=parameters,
                status=NodeStatus.REJECTED.value,
                error=result.reason,
                branch_condition=branch_condition,
                base_changes=[],
                result_instance=instance,
                layer_state_cache=layer_state_cache,
            )
            return [node]

        else:
            # Constraint violation or other error
            if result.after:
                new_snapshot = capture_snapshot(result.after, self.registry_manager, parent_node.snapshot)
            else:
                new_snapshot = parent_node.snapshot
            node = create_or_merge_node(
                tree=tree,
                parent_node=parent_node,
                snapshot=new_snapshot,
                action_name=action.name,
                parameters=parameters,
                status=result.status,
                error=result.reason or "; ".join(result.violations),
                branch_condition=None,
                base_changes=changes,
                result_instance=result.after if result.after else instance,
                layer_state_cache=layer_state_cache,
            )
            return [node]
