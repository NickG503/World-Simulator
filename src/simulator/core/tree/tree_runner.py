"""
Tree-based simulation runner.

Executes simulations building a tree/DAG structure where nodes represent
world states and edges represent action transitions. Supports branching
on unknown attributes and merging of equivalent states.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from simulator.core.actions.action import Action
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.simulation_runner import ActionRequest
from simulator.core.tree.mixins import (
    BranchCreationMixin,
    ConditionDetectionMixin,
    PostconditionBranchingMixin,
    PreconditionBranchingMixin,
)
from simulator.core.tree.models import (
    BranchCondition,
    NodeStatus,
    SimulationTree,
    TreeNode,
)
from simulator.core.tree.node_factory import (
    create_error_node,
    create_or_merge_node,
    create_root_node,
)
from simulator.core.tree.snapshot_utils import capture_snapshot
from simulator.core.tree.utils.evaluation import evaluate_condition_for_value

logger = logging.getLogger(__name__)


class TreeSimulationRunner(
    ConditionDetectionMixin,
    BranchCreationMixin,
    PreconditionBranchingMixin,
    PostconditionBranchingMixin,
):
    """Executes simulations building a tree/DAG structure with branching support."""

    def __init__(self, registry_manager: RegistryManager):
        self.registry_manager = registry_manager
        self.engine = TransitionEngine(registry_manager)

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    def run(
        self,
        object_type: str,
        actions: List[Union[ActionRequest, Dict[str, Any]]],
        simulation_id: Optional[str] = None,
        verbose: bool = False,
        initial_values: Optional[Dict[str, str]] = None,
    ) -> SimulationTree:
        """Run a simulation and build the execution tree."""
        if not simulation_id:
            simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        obj_type = self.registry_manager.objects.get(object_type)
        from simulator.io.loaders.object_loader import instantiate_default

        obj_instance = instantiate_default(obj_type, self.registry_manager)

        if initial_values:
            self._apply_initial_values(obj_instance, initial_values)
            if verbose:
                for path, value in initial_values.items():
                    logger.info("Set initial value: %s = %s", path, value)

        tree = SimulationTree(
            simulation_id=simulation_id,
            object_type=object_type,
            object_name=object_type,
        )

        root_snapshot = capture_snapshot(obj_instance, self.registry_manager)
        root_node = create_root_node(tree, root_snapshot)
        tree.add_node(root_node)

        if verbose:
            logger.info("Created root node: %s", root_node.id)

        action_requests = self._parse_action_requests(actions)
        leaves: List[Tuple[TreeNode, ObjectInstance]] = [(root_node, obj_instance)]

        for request in action_requests:
            new_leaves: List[Tuple[TreeNode, ObjectInstance]] = []
            layer_state_cache: Dict[str, Tuple[TreeNode, ObjectInstance]] = {}
            seen_node_ids: set = set()

            for current_node, current_instance in leaves:
                results = self._process_action_multi(
                    tree=tree,
                    instance=current_instance,
                    parent_node=current_node,
                    action_name=request.name,
                    parameters=request.parameters,
                    verbose=verbose,
                    layer_state_cache=layer_state_cache,
                )

                for result in results:
                    if result.node.id not in seen_node_ids:
                        new_leaves.append((result.node, result.instance or current_instance))
                        seen_node_ids.add(result.node.id)

                if verbose:
                    for result in results:
                        logger.info("Created node: %s", result.node.describe())

            leaves = new_leaves

            if verbose and layer_state_cache:
                merged_count = sum(1 for n, _ in layer_state_cache.values() if n.has_multiple_parents)
                if merged_count > 0:
                    logger.info("Layer deduplication: %d nodes merged", merged_count)

        return tree

    # =========================================================================
    # Action Processing
    # =========================================================================

    def _process_action_multi(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> List["ActionResult"]:
        """Process action and return results for all branches."""
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

        parent_children = tree.nodes[parent_node.id].children_ids
        if len(parent_children) > 1:
            results = []
            for child_id in parent_children:
                child_node = tree.nodes[child_id]
                bc = child_node.branch_condition
                if bc and bc.attribute:
                    values = bc.value if isinstance(bc.value, list) else [bc.value]
                    constrained_instance = self._clone_instance_with_values(instance, bc.attribute, values)
                else:
                    constrained_instance = instance.deep_copy()

                if child_node.action_status == NodeStatus.OK.value:
                    engine_result = self.engine.apply_action(constrained_instance, result.action, parameters)
                    child_instance = engine_result.after if engine_result.after else constrained_instance
                else:
                    child_instance = constrained_instance
                results.append(ActionResult(node=child_node, instance=child_instance, action=result.action))
            return results

        return [result]

    def _process_action(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> "ActionResult":
        """Process action, creating branches for unknown attributes."""
        if layer_state_cache is None:
            layer_state_cache = {}

        action = self.registry_manager.create_behavior_enhanced_action(instance.type.name, action_name)

        if not action:
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

        parent_snapshot = parent_node.snapshot if parent_node else None

        compound_precond = self._get_compound_precondition(action, instance, parent_snapshot)
        precond_unknown = self._get_unknown_precondition_attribute(action, instance, parent_snapshot)
        postcond_unknown = self._get_unknown_postcondition_attribute(action, instance, parent_snapshot)

        if verbose:
            if compound_precond or precond_unknown or postcond_unknown:
                logger.info(
                    "Branch points detected - compound: %s, precondition: %s, postcondition: %s",
                    type(compound_precond[0]).__name__ if compound_precond else None,
                    precond_unknown,
                    postcond_unknown,
                )

        child_nodes: List[TreeNode] = []

        if compound_precond:
            compound_cond, unknowns = compound_precond
            if isinstance(compound_cond, OrCondition):
                child_nodes = self._create_or_precondition_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    condition=compound_cond,
                    unknowns=unknowns,
                    postcond_attr=postcond_unknown,
                    layer_state_cache=layer_state_cache,
                )
            else:
                child_nodes = self._create_and_precondition_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    condition=compound_cond,
                    unknowns=unknowns,
                    postcond_attr=postcond_unknown,
                    layer_state_cache=layer_state_cache,
                )
            if verbose:
                logger.info("Created %d compound precondition branches", len(child_nodes))
        elif precond_unknown:
            child_nodes = self._create_combined_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                precond_attr=precond_unknown,
                postcond_attr=postcond_unknown,
                layer_state_cache=layer_state_cache,
            )
            if verbose:
                logger.info("Created %d combined branches", len(child_nodes))
        else:
            precond_result = self.engine.apply_action(instance, action, parameters)

            if precond_result.status == "rejected":
                child_nodes = self._apply_action_linear(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    layer_state_cache=layer_state_cache,
                )
            elif postcond_unknown:
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
                child_nodes = self._apply_action_linear(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    layer_state_cache=layer_state_cache,
                )

        if child_nodes:
            if len(child_nodes) > 1:
                tree.add_branch_nodes(parent_node.id, child_nodes)
            else:
                for node in child_nodes:
                    tree.add_node(node)

            primary_node = child_nodes[0]
            new_instance = None

            if primary_node.action_status == NodeStatus.OK.value:
                result = self.engine.apply_action(instance, action, parameters)
                if result.after:
                    new_instance = result.after

            return ActionResult(node=primary_node, instance=new_instance, action=action)

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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> List[TreeNode]:
        """Apply action linearly (no branching), returning single node."""
        if layer_state_cache is None:
            layer_state_cache = {}

        result = self.engine.apply_action(instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        if result.status == "ok":
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

    # =========================================================================
    # Branch Condition Extraction
    # =========================================================================

    def _extract_postcondition_branch(self, action: Action, instance: ObjectInstance) -> Optional[BranchCondition]:
        """Extract branch condition from conditional effects."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
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
        self, action: Action, instance: ObjectInstance, reason: Optional[str]
    ) -> Optional[BranchCondition]:
        """Extract branch condition from precondition failure."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

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

    # =========================================================================
    # Utilities
    # =========================================================================

    def _evaluate_condition_for_value(self, condition: Any, value: str) -> bool:
        """Check if a specific value would pass a condition."""
        return evaluate_condition_for_value(condition, value)

    def _parse_action_requests(self, actions: List[Union[ActionRequest, Dict[str, Any]]]) -> List[ActionRequest]:
        """Parse action list into ActionRequest objects."""
        return [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action) for action in actions
        ]

    def _apply_initial_values(self, instance: ObjectInstance, values: Dict[str, str]) -> None:
        """Apply initial value overrides to an object instance."""
        for path, value in values.items():
            parts = path.split(".")
            if len(parts) == 2:
                part_name, attr_name = parts
                if part_name in instance.parts:
                    part_inst = instance.parts[part_name]
                    if attr_name in part_inst.attributes:
                        attr_inst = part_inst.attributes[attr_name]
                        attr_inst.current_value = value
                        attr_inst.last_known_value = value if value != "unknown" else None
            elif len(parts) == 1:
                attr_name = parts[0]
                if attr_name in instance.global_attributes:
                    attr_inst = instance.global_attributes[attr_name]
                    attr_inst.current_value = value
                    attr_inst.last_known_value = value if value != "unknown" else None

    def _build_changes_list(self, changes: List[Any]) -> List[Dict[str, Any]]:
        """Build serializable changes list, filtering info/internal/no-op entries."""
        result = []
        for c in changes:
            normalized = self._normalize_change(c)
            if normalized:
                result.append(normalized)
        return result

    def _normalize_change(self, change: Any) -> Optional[Dict[str, Any]]:
        """Normalize a change (dict or object) to dict format."""
        if isinstance(change, dict):
            attr = change.get("attribute", "")
            before = change.get("before")
            after = change.get("after")
            kind = change.get("kind", "value")
        elif hasattr(change, "attribute"):
            attr = change.attribute
            before = change.before
            after = change.after
            kind = getattr(change, "kind", "value")
        else:
            return None

        if before == after or kind == "info" or attr.startswith("["):
            return None

        return {"attribute": attr, "before": before, "after": after, "kind": kind}

    def _build_precondition_error(self, action: Action, attr_path: str, actual_values: List[str]) -> str:
        """Build detailed precondition error message."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.utils.error_formatting import format_precondition_error

        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                if condition.target.to_string() == attr_path:
                    actual = actual_values[0] if len(actual_values) == 1 else actual_values
                    msg = format_precondition_error(
                        attr_path=attr_path,
                        operator=condition.operator,
                        expected_value=condition.value,
                        actual_value=actual,
                    )
                    return f"Precondition failed: {msg}"

        actual_str = actual_values[0] if len(actual_values) == 1 else "{" + ", ".join(actual_values) + "}"
        return f"Precondition failed: {attr_path} (actual: {actual_str})"

    # =========================================================================
    # Serialization
    # =========================================================================

    def save_tree_to_yaml(self, tree: SimulationTree, file_path: str) -> None:
        """Save simulation tree to YAML file."""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        data = tree.to_dict()
        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)


@dataclass
class ActionResult:
    """Result of processing an action."""

    node: TreeNode
    instance: Optional[ObjectInstance] = None
    action: Optional[Action] = None


__all__ = ["TreeSimulationRunner", "ActionResult"]
