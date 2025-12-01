"""
Tree-based simulation runner.

This module provides the TreeSimulationRunner which executes simulations
building a tree structure. Each node represents a world state and each
edge represents an action transition.

Architecture:
------------
Phase 1 (Current): Linear execution
    - All attribute values are known
    - Single path through tree
    - Each action produces exactly one child node

Phase 2 (Future): Branching on unknowns
    - When a precondition checks an unknown attribute:
        → Branch into success/fail paths
    - When a postcondition (if/elif/else) checks an unknown attribute:
        → Branch into N paths (one per condition case + else)
    - Tree can have multiple leaf nodes representing different world states

The key extension points for Phase 2:
    1. _should_branch_on_precondition() - determines if branching needed
    2. _should_branch_on_postcondition() - determines if branching needed
    3. _create_precondition_branches() - creates success/fail branch nodes
    4. _create_postcondition_branches() - creates case branch nodes
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from simulator.core.actions.action import Action
from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.simulation_runner import (
    ActionRequest,
    AttributeSnapshot,
    ObjectStateSnapshot,
    PartStateSnapshot,
)
from simulator.core.tree.models import (
    BranchCondition,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)

logger = logging.getLogger(__name__)


class TreeSimulationRunner:
    """
    Executes simulation building a tree structure.

    The runner processes actions sequentially, creating nodes for each
    state transition. In Phase 1, this produces a linear path. In Phase 2,
    it will produce a tree with branches.

    Attributes:
        registry_manager: Access to objects, actions, and spaces
        engine: TransitionEngine for applying actions
    """

    def __init__(self, registry_manager: RegistryManager):
        """
        Initialize the runner.

        Args:
            registry_manager: Registry manager with loaded KB
        """
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
    ) -> SimulationTree:
        """
        Run a simulation and build the execution tree.

        Args:
            object_type: Type of object to simulate (e.g., 'flashlight')
            actions: List of actions to execute (can be ActionRequest or dict)
            simulation_id: Optional ID for the simulation (auto-generated if None)
            verbose: Whether to log detailed progress

        Returns:
            SimulationTree containing all nodes and the execution path
        """
        # Generate simulation ID if not provided
        if not simulation_id:
            simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create object instance
        obj_type = self.registry_manager.objects.get(object_type)
        from simulator.io.loaders.object_loader import instantiate_default

        obj_instance = instantiate_default(obj_type, self.registry_manager)

        # Initialize tree
        tree = SimulationTree(
            simulation_id=simulation_id,
            object_type=object_type,
            object_name=object_type,
        )

        # Create root node with initial state
        root_node = self._create_root_node(tree, obj_instance)
        tree.add_node(root_node)

        if verbose:
            logger.info("Created root node: %s", root_node.id)

        # Process actions sequentially
        current_instance = obj_instance
        current_node = root_node

        action_requests = self._parse_action_requests(actions)

        for request in action_requests:
            result = self._process_action(
                tree=tree,
                instance=current_instance,
                parent_node=current_node,
                action_name=request.name,
                parameters=request.parameters,
                verbose=verbose,
            )

            # Update current state
            current_node = result.node
            if result.instance:
                current_instance = result.instance

            if verbose:
                logger.info("Created node: %s", current_node.describe())

        return tree

    # =========================================================================
    # Action Processing
    # =========================================================================

    def _process_action(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
    ) -> "ActionResult":
        """
        Process a single action and create resulting node(s).

        This is the main extension point for Phase 2 branching.

        Args:
            tree: The simulation tree
            instance: Current object instance
            parent_node: The node to branch from
            action_name: Name of action to execute
            parameters: Action parameters
            verbose: Log progress

        Returns:
            ActionResult with the new node and optionally updated instance
        """
        # Resolve action
        action = self.registry_manager.create_behavior_enhanced_action(instance.type.name, action_name)

        if not action:
            # Action not found - create error node
            node = self._create_error_node(
                tree=tree,
                parent_node=parent_node,
                instance=instance,
                action_name=action_name,
                parameters=parameters,
                error=f"Action '{action_name}' not found for {instance.type.name}",
            )
            tree.add_node(node)
            return ActionResult(node=node, instance=None)

        # Phase 1: Check if we would need to branch (for future use)
        # In Phase 2, this is where branching decisions would be made
        precond_unknown = self._get_unknown_precondition_attribute(action, instance)
        postcond_unknown = self._get_unknown_postcondition_attribute(action, instance)

        if verbose and (precond_unknown or postcond_unknown):
            logger.debug(
                "Potential branch points - precondition: %s, postcondition: %s",
                precond_unknown,
                postcond_unknown,
            )

        # Phase 1: Linear execution - apply action directly
        child_nodes = self._apply_action_linear(
            tree=tree,
            instance=instance,
            parent_node=parent_node,
            action=action,
            parameters=parameters,
        )

        # Add the node(s) to tree
        if child_nodes:
            for node in child_nodes:
                tree.add_node(node)

            # Return first node and update instance if succeeded
            primary_node = child_nodes[0]
            new_instance = None

            if primary_node.action_status == NodeStatus.OK.value:
                result = self.engine.apply_action(instance, action, parameters)
                if result.after:
                    new_instance = result.after

            return ActionResult(node=primary_node, instance=new_instance)

        # Should not happen, but handle gracefully
        error_node = self._create_error_node(
            tree=tree,
            parent_node=parent_node,
            instance=instance,
            action_name=action_name,
            parameters=parameters,
            error="No nodes created from action",
        )
        tree.add_node(error_node)
        return ActionResult(node=error_node, instance=None)

    def _apply_action_linear(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
    ) -> List[TreeNode]:
        """
        Apply an action in linear mode (Phase 1).

        Always returns exactly one node representing the action outcome.

        Args:
            tree: Simulation tree for node ID generation
            instance: Current object instance
            parent_node: Parent node
            action: Action to apply
            parameters: Action parameters

        Returns:
            List containing single TreeNode
        """
        result = self.engine.apply_action(instance, action, parameters)

        # Build changes list
        changes = self._build_changes_list(result.changes)

        if result.status == "ok":
            # Success - capture new state
            new_snapshot = self._capture_snapshot(result.after) if result.after else parent_node.snapshot

            branch_condition = self._extract_postcondition_branch(action, instance)

            return [
                TreeNode(
                    id=tree.generate_node_id(),
                    snapshot=new_snapshot,
                    parent_id=parent_node.id,
                    action_name=action.name,
                    action_parameters=parameters,
                    action_status=NodeStatus.OK.value,
                    branch_condition=branch_condition,
                    changes=changes,
                )
            ]

        elif result.status == "rejected":
            # Precondition failed
            branch_condition = self._extract_precondition_failure(action, instance, result.reason)

            return [
                TreeNode(
                    id=tree.generate_node_id(),
                    snapshot=parent_node.snapshot,  # State unchanged
                    parent_id=parent_node.id,
                    action_name=action.name,
                    action_parameters=parameters,
                    action_status=NodeStatus.REJECTED.value,
                    action_error=result.reason,
                    branch_condition=branch_condition,
                    changes=[],
                )
            ]

        else:
            # Constraint violation or other error
            return [
                TreeNode(
                    id=tree.generate_node_id(),
                    snapshot=(self._capture_snapshot(result.after) if result.after else parent_node.snapshot),
                    parent_id=parent_node.id,
                    action_name=action.name,
                    action_parameters=parameters,
                    action_status=result.status,
                    action_error=result.reason or "; ".join(result.violations),
                    changes=changes,
                )
            ]

    # =========================================================================
    # Phase 2 Extension Points (Branching)
    # =========================================================================

    def _get_unknown_precondition_attribute(self, action: Action, instance: ObjectInstance) -> Optional[str]:
        """
        Get the unknown attribute in precondition that would cause branching.

        Phase 2: This identifies when we need to branch on precondition.

        Returns:
            Attribute path if unknown, None if all known
        """
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                try:
                    ai = condition.target.resolve(instance)
                    if ai.current_value == "unknown":
                        return condition.target.to_string()
                except Exception:
                    pass
        return None

    def _get_unknown_postcondition_attribute(self, action: Action, instance: ObjectInstance) -> Optional[str]:
        """
        Get the unknown attribute in postcondition that would cause branching.

        Phase 2: This identifies when we need to branch on postcondition.

        Returns:
            Attribute path if unknown, None if all known
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
                        if ai.current_value == "unknown":
                            return cond.target.to_string()
                    except Exception:
                        pass
        return None

    def _get_postcondition_branch_options(self, action: Action, attribute_path: str) -> List[Tuple[str, str]]:
        """
        Get all possible branch options for a postcondition attribute.

        Phase 2: This returns the options for branching.
        Returns list of (value, branch_type) tuples.

        Example for if battery.level == high / elif medium / else:
            [("high", "if"), ("medium", "elif"), ("low,empty", "else")]
        """
        # TODO: Implement in Phase 2
        # This requires analyzing the conditional effect structure
        return []

    # =========================================================================
    # Node Creation Helpers
    # =========================================================================

    def _create_root_node(self, tree: SimulationTree, instance: ObjectInstance) -> TreeNode:
        """Create the root node with initial state."""
        return TreeNode(
            id=tree.generate_node_id(),  # state0
            snapshot=self._capture_snapshot(instance),
            action_name=None,  # Root has no action
        )

    def _create_error_node(
        self,
        tree: SimulationTree,
        parent_node: TreeNode,
        instance: ObjectInstance,
        action_name: str,
        parameters: Dict[str, str],
        error: str,
    ) -> TreeNode:
        """Create an error node for action failures."""
        return TreeNode(
            id=tree.generate_node_id(),
            snapshot=self._capture_snapshot(instance),
            parent_id=parent_node.id,
            action_name=action_name,
            action_parameters=parameters,
            action_status=NodeStatus.ERROR.value,
            action_error=error,
        )

    # =========================================================================
    # Branch Condition Extraction
    # =========================================================================

    def _extract_postcondition_branch(self, action: Action, instance: ObjectInstance) -> Optional[BranchCondition]:
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
        self, action: Action, instance: ObjectInstance, reason: Optional[str]
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

    # =========================================================================
    # State Capture
    # =========================================================================

    def _capture_snapshot(self, obj_instance: ObjectInstance) -> WorldSnapshot:
        """Capture the current object state as a WorldSnapshot."""
        parts: Dict[str, PartStateSnapshot] = {}

        for part_name, part_instance in obj_instance.parts.items():
            attrs: Dict[str, AttributeSnapshot] = {}
            for attr_name, attr_instance in part_instance.attributes.items():
                attrs[attr_name] = AttributeSnapshot(
                    value=attr_instance.current_value,
                    trend=attr_instance.trend,
                    last_known_value=attr_instance.last_known_value,
                    last_trend_direction=attr_instance.last_trend_direction,
                    space_id=attr_instance.spec.space_id,
                )
            parts[part_name] = PartStateSnapshot(attributes=attrs)

        global_attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in obj_instance.global_attributes.items():
            global_attrs[attr_name] = AttributeSnapshot(
                value=attr_instance.current_value,
                trend=attr_instance.trend,
                last_known_value=attr_instance.last_known_value,
                last_trend_direction=attr_instance.last_trend_direction,
                space_id=attr_instance.spec.space_id,
            )

        object_state = ObjectStateSnapshot(
            type=obj_instance.type.name,
            parts=parts,
            global_attributes=global_attrs,
        )

        return WorldSnapshot(object_state=object_state)

    # =========================================================================
    # Utilities
    # =========================================================================

    def _parse_action_requests(self, actions: List[Union[ActionRequest, Dict[str, Any]]]) -> List[ActionRequest]:
        """Parse action list into ActionRequest objects."""
        return [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action) for action in actions
        ]

    def _build_changes_list(self, changes: List[Any]) -> List[Dict[str, Any]]:
        """Build serializable changes list from DiffEntry objects."""
        return [
            {
                "attribute": c.attribute,
                "before": c.before,
                "after": c.after,
                "kind": c.kind,
            }
            for c in changes
            if c.kind != "info" and not c.attribute.startswith("[")
        ]

    # =========================================================================
    # Serialization
    # =========================================================================

    def save_tree_to_yaml(self, tree: SimulationTree, file_path: str) -> None:
        """
        Save simulation tree to YAML file.

        Args:
            tree: Simulation tree to save
            file_path: Output file path
        """
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        data = tree.to_dict()

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)


class ActionResult:
    """Result of processing an action."""

    def __init__(self, node: TreeNode, instance: Optional[ObjectInstance]):
        """
        Args:
            node: The node created for this action
            instance: Updated instance if action succeeded, None otherwise
        """
        self.node = node
        self.instance = instance


__all__ = ["TreeSimulationRunner", "ActionResult"]
