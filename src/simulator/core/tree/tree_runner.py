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
        initial_values: Optional[Dict[str, str]] = None,
    ) -> SimulationTree:
        """
        Run a simulation and build the execution tree.

        Args:
            object_type: Type of object to simulate (e.g., 'flashlight')
            actions: List of actions to execute (can be ActionRequest or dict)
            simulation_id: Optional ID for the simulation (auto-generated if None)
            verbose: Whether to log detailed progress
            initial_values: Optional dict of attribute paths to initial values
                           e.g., {"battery.level": "unknown", "switch.position": "on"}

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

        # Apply initial value overrides
        if initial_values:
            self._apply_initial_values(obj_instance, initial_values)
            if verbose:
                for path, value in initial_values.items():
                    logger.info("Set initial value: %s = %s", path, value)

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

        # Process actions on all branches
        # Each branch has: (node, instance) tuple
        action_requests = self._parse_action_requests(actions)

        # Start with root as the only leaf
        leaves: List[Tuple[TreeNode, ObjectInstance]] = [(root_node, obj_instance)]

        for request in action_requests:
            new_leaves: List[Tuple[TreeNode, ObjectInstance]] = []

            for current_node, current_instance in leaves:
                # Process action on this branch
                results = self._process_action_multi(
                    tree=tree,
                    instance=current_instance,
                    parent_node=current_node,
                    action_name=request.name,
                    parameters=request.parameters,
                    verbose=verbose,
                )

                # Each result becomes a new leaf
                for result in results:
                    new_leaves.append((result.node, result.instance or current_instance))

                if verbose:
                    for result in results:
                        logger.info("Created node: %s", result.node.describe())

            leaves = new_leaves

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
    ) -> List["ActionResult"]:
        """
        Process a single action and return results for ALL branches.

        This ensures subsequent actions are applied to all branches,
        including failed branches (where the world state doesn't change).

        Returns:
            List of ActionResult, one for each branch created
        """
        result = self._process_action(
            tree=tree,
            instance=instance,
            parent_node=parent_node,
            action_name=action_name,
            parameters=parameters,
            verbose=verbose,
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
                    values = bc.value if isinstance(bc.value, list) else [bc.value]
                    constrained_instance = self._clone_instance_with_values(instance, bc.attribute, values)
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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action_name: str,
        parameters: Dict[str, str],
        verbose: bool = False,
    ) -> "ActionResult":
        """
        Process a single action and create resulting node(s).

        Phase 2: Implements branching logic:
        - If precondition has unknown attribute → 2 branches (success/fail)
        - If postcondition has unknown attribute → N+1 branches (if/elif/else)

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
            return ActionResult(node=node, instance=None, action=None)

        # Check for unknown attributes that would cause branching
        # Pass parent snapshot to detect value sets from trends
        parent_snapshot = parent_node.snapshot if parent_node else None
        precond_unknown = self._get_unknown_precondition_attribute(action, instance, parent_snapshot)
        postcond_unknown = self._get_unknown_postcondition_attribute(action, instance, parent_snapshot)

        if verbose:
            if precond_unknown or postcond_unknown:
                logger.info(
                    "Branch points detected - precondition: %s, postcondition: %s",
                    precond_unknown,
                    postcond_unknown,
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
                )
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
        error_node = self._create_error_node(
            tree=tree,
            parent_node=parent_node,
            instance=instance,
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
            # Success - capture new state (preserve value sets from parent)
            new_snapshot = (
                self._capture_snapshot(result.after, parent_node.snapshot) if result.after else parent_node.snapshot
            )

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
            new_snapshot = (
                self._capture_snapshot(result.after, parent_node.snapshot) if result.after else parent_node.snapshot
            )
            return [
                TreeNode(
                    id=tree.generate_node_id(),
                    snapshot=new_snapshot,
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

    def _get_unknown_precondition_attribute(
        self, action: Action, instance: ObjectInstance, parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Optional[str]:
        """
        Get the unknown attribute in precondition that would cause branching.

        Phase 2: This identifies when we need to branch on precondition.

        An attribute is considered "unknown" (requiring branching) if:
        - Its current_value is "unknown"
        - It's a value SET (list) in the parent snapshot (e.g., from a trend)

        Returns:
            Attribute path if unknown/multi-valued, None if all known single values
        """
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                try:
                    ai = condition.target.resolve(instance)
                    attr_path = condition.target.to_string()

                    # Check if current value is "unknown"
                    if ai.current_value == "unknown":
                        return attr_path

                    # Check if parent snapshot has a value set for this attribute
                    if parent_snapshot:
                        snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                        if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                            return attr_path
                except Exception:
                    pass
        return None

    def _get_unknown_postcondition_attribute(
        self, action: Action, instance: ObjectInstance, parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Optional[str]:
        """
        Get the unknown attribute in postcondition that would cause branching.

        Phase 2: This identifies when we need to branch on postcondition.

        An attribute is considered "unknown" (requiring branching) if:
        - Its current_value is "unknown"
        - It's a value SET (list) in the parent snapshot (e.g., from a trend)

        Returns:
            Attribute path if unknown/multi-valued, None if all known single values
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
                        attr_path = cond.target.to_string()

                        # Check if current value is "unknown"
                        if ai.current_value == "unknown":
                            return attr_path

                        # Check if parent snapshot has a value set for this attribute
                        if parent_snapshot:
                            snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                            if isinstance(snapshot_value, list) and len(snapshot_value) > 1:
                                return attr_path
                    except Exception:
                        pass
        return None

    def _get_postcondition_branch_options(
        self, action: Action, instance: ObjectInstance, attribute_path: str
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

        # Add else branch with remaining values (if any values not covered)
        if all_values and used_values:
            remaining = [v for v in all_values if v not in used_values]
            if remaining:
                # No explicit else effects in flat structure - just empty effects
                options.append((remaining, "else", []))

        return options

    # =========================================================================
    # Value Set Computation (Phase 2)
    # =========================================================================

    def _compute_value_set_from_trend(self, current_value: str, trend: str, space_id: str) -> List[str]:
        """
        Compute possible values based on trend direction.

        Args:
            current_value: Current known value (e.g., "medium")
            trend: Trend direction ("up" or "down")
            space_id: ID of the qualitative space

        Returns:
            List of possible values based on trend.
            - trend "down" from "medium" → ["empty", "low", "medium"]
            - trend "up" from "medium" → ["medium", "high", "full"]

        If the space or current value is not found, returns [current_value].
        """
        try:
            space = self.registry_manager.spaces.get(space_id)
            if not space:
                return [current_value]

            levels = list(space.levels)  # Ordered from low to high
            if current_value not in levels:
                return [current_value]

            current_idx = levels.index(current_value)

            if trend == "down":
                # All values at or below current (from lowest to current)
                return levels[: current_idx + 1]
            elif trend == "up":
                # All values at or above current (from current to highest)
                return levels[current_idx:]
            else:
                return [current_value]
        except Exception:
            return [current_value]

    def _get_attribute_space_id(self, instance: ObjectInstance, attr_path: str) -> Optional[str]:
        """
        Get the space ID for an attribute.

        Args:
            instance: Object instance
            attr_path: Attribute path like "battery.level"

        Returns:
            Space ID or None if not found
        """
        try:
            parts = attr_path.split(".")
            if len(parts) == 2:
                part_name, attr_name = parts
                part_inst = instance.parts.get(part_name)
                if part_inst:
                    attr_inst = part_inst.attributes.get(attr_name)
                    if attr_inst:
                        return attr_inst.spec.space_id
            elif len(parts) == 1:
                attr_inst = instance.global_attributes.get(parts[0])
                if attr_inst:
                    return attr_inst.spec.space_id
        except Exception:
            pass
        return None

    def _get_all_space_values(self, space_id: str) -> List[str]:
        """Get all values in a space, ordered."""
        try:
            space = self.registry_manager.spaces.get(space_id)
            return list(space.levels) if space else []
        except Exception:
            return []

    def _get_precondition_condition(self, action: Action):
        """Get the first precondition condition that checks an attribute."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        for condition in action.preconditions:
            if isinstance(condition, AttributeCondition):
                return condition
        return None

    def _evaluate_condition_for_value(self, condition, value: str) -> bool:
        """
        Check if a specific value would pass a condition.

        Args:
            condition: The condition to evaluate
            value: The value to test

        Returns:
            True if the condition would pass with this value
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        if not isinstance(condition, AttributeCondition):
            return True

        if condition.operator == "equals":
            return value == condition.value
        elif condition.operator == "not_equals":
            return value != condition.value
        elif condition.operator == "in":
            # Check if value is in the list
            if isinstance(condition.value, list):
                return value in condition.value
            return value == condition.value
        elif condition.operator == "not_in":
            # Check if value is NOT in the list
            if isinstance(condition.value, list):
                return value not in condition.value
            return value != condition.value
        elif condition.operator in ("gt", ">"):
            # For qualitative spaces, compare by order
            return False  # Simplified for now
        elif condition.operator in ("lt", "<"):
            return False  # Simplified for now
        return True

    # =========================================================================
    # Phase 2: Branching Methods
    # =========================================================================

    def _create_precondition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
    ) -> List[TreeNode]:
        """
        Create 2 branches for precondition: success and fail paths.

        When the precondition checks an unknown attribute or value set, we split into:
        - Success branch: attribute values that would satisfy the precondition
        - Fail branch: attribute values that would NOT satisfy the precondition

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            attr_path: Path to the unknown/multi-valued attribute

        Returns:
            List of 2 TreeNodes [success_node, fail_node]
        """
        condition = self._get_precondition_condition(action)
        space_id = self._get_attribute_space_id(instance, attr_path)

        if not condition or not space_id:
            # Fallback to linear execution
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        # Get possible values: from parent snapshot's value set, or all space values
        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(attr_path)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            # Fall back to all space values (for explicit "unknown")
            possible_values = self._get_all_space_values(space_id)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        # Partition values into passing and failing
        passing_values = [v for v in possible_values if self._evaluate_condition_for_value(condition, v)]
        failing_values = [v for v in possible_values if not self._evaluate_condition_for_value(condition, v)]

        branches: List[TreeNode] = []

        # Create SUCCESS branch (precondition passes)
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

        # Create FAIL branch (precondition fails)
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

    def _create_combined_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        precond_attr: str,
        postcond_attr: Optional[str],
    ) -> List[TreeNode]:
        """
        Create branches considering BOTH precondition and postcondition.

        Logic:
        1. Partition values for precondition into pass/fail sets
        2. Create FAIL branch with fail values (no effects applied)
        3. For SUCCESS values, further split by postcondition if/elif/else:
           - If postcond_attr is None: single success branch
           - If postcond_attr == precond_attr: intersect with pass values
           - If postcond_attr != precond_attr: split by postcondition cases

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            precond_attr: Attribute path checked in precondition
            postcond_attr: Attribute path checked in postcondition (may be None or same)

        Returns:
            List of branches: 1 fail + N success sub-branches
        """
        condition = self._get_precondition_condition(action)
        space_id = self._get_attribute_space_id(instance, precond_attr)

        if not condition or not space_id:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        # Get possible values from parent snapshot or space
        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(precond_attr)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            possible_values = self._get_all_space_values(space_id)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

        # Partition into passing and failing values
        pass_values = [v for v in possible_values if self._evaluate_condition_for_value(condition, v)]
        fail_values = [v for v in possible_values if not self._evaluate_condition_for_value(condition, v)]

        branches: List[TreeNode] = []

        # 1. Create SUCCESS branches first (so they're primary in current_path)
        if pass_values:
            if postcond_attr is None:
                # No postcondition branching - single success branch
                success_node = self._create_branch_success_node(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    attr_path=precond_attr,
                    values=pass_values,
                )
                branches.append(success_node)
            else:
                # Further split by postcondition
                success_branches = self._create_postcondition_success_branches(
                    tree=tree,
                    instance=instance,
                    parent_node=parent_node,
                    action=action,
                    parameters=parameters,
                    precond_attr=precond_attr,
                    precond_pass_values=pass_values,
                    postcond_attr=postcond_attr,
                )
                branches.extend(success_branches)

        # 2. Create FAIL branch (if any fail values)
        if fail_values:
            fail_node = self._create_branch_fail_node(
                tree=tree,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                attr_path=precond_attr,
                values=fail_values,
            )
            branches.append(fail_node)

        return branches

    def _create_postcondition_success_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        precond_attr: str,
        precond_pass_values: List[str],
        postcond_attr: str,
    ) -> List[TreeNode]:
        """
        Create N branches for postcondition, constrained by precondition pass values.

        If same attribute: intersect postcondition cases with pass values.
        If different attribute: each postcondition branch has full pass values for precond_attr.

        Returns:
            List of N TreeNodes for success branches
        """
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
            )
            branches.append(node)

        return branches

    def _create_postcond_case_node(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        precond_attr: str,
        precond_values: List[str],
        postcond_attr: str,
        postcond_value: Union[str, List[str]],
        branch_type: str,
        effects: List[Any],
    ) -> TreeNode:
        """Create a node for a postcondition case with effects applied."""
        from copy import deepcopy

        # Clone instance and set the first pass value for action application
        new_instance = deepcopy(instance)

        # For action application, set to first value (action needs single value)
        if precond_attr == postcond_attr:
            # Same attribute - use the constrained values from intersection
            if isinstance(postcond_value, list):
                self._set_attribute_value(new_instance, precond_attr, postcond_value[0])
            else:
                self._set_attribute_value(new_instance, precond_attr, postcond_value)
        else:
            # Different attributes - set precond attr to first pass value
            self._set_attribute_value(new_instance, precond_attr, precond_values[0])
            if isinstance(postcond_value, list):
                self._set_attribute_value(new_instance, postcond_attr, postcond_value[0])
            else:
                self._set_attribute_value(new_instance, postcond_attr, postcond_value)

        # Apply effects for this branch using the engine
        action_result = self.engine.apply_action(new_instance, action, parameters)
        raw_changes = action_result.changes if action_result else []

        # Build changes list from raw changes
        changes = self._build_changes_list_from_raw(raw_changes)

        # Add narrowing changes for the constrained attributes
        # For precond_attr: narrowed from parent's value to precond_values
        narrowing = self._compute_narrowing_change(parent_node.snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            # Also add narrowing for postcond_attr if different
            postcond_vals = postcond_value if isinstance(postcond_value, list) else [postcond_value]
            narrowing.extend(self._compute_narrowing_change(parent_node.snapshot, postcond_attr, postcond_vals))
        changes = narrowing + changes  # Put narrowing first

        # Use the resulting instance after effects are applied
        result_instance = action_result.after if action_result and action_result.after else new_instance

        # Capture snapshot then update with constrained values
        snapshot = self._capture_snapshot(result_instance, parent_node.snapshot)

        # Update the snapshot with the constrained value set for this branch
        self._update_snapshot_attribute(snapshot, precond_attr, precond_values)
        if precond_attr != postcond_attr:
            if isinstance(postcond_value, list):
                self._update_snapshot_attribute(snapshot, postcond_attr, postcond_value)
            else:
                self._update_snapshot_attribute(snapshot, postcond_attr, [postcond_value])

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

        return TreeNode(
            id=tree.generate_node_id(),
            snapshot=snapshot,
            parent_id=parent_node.id,
            action_name=action.name,
            action_parameters=parameters,
            action_status=NodeStatus.OK.value,
            branch_condition=branch_condition,
            changes=changes,
        )

    def _set_attribute_values(self, instance: ObjectInstance, attr_path: str, values: List[str]) -> None:
        """Set an attribute to a list of values (or single value if list has one element)."""
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            part_inst = instance.parts.get(part_name)
            if part_inst:
                attr_inst = part_inst.attributes.get(attr_name)
                if attr_inst:
                    # Set to single value or keep as "unknown" if multiple
                    attr_inst.current_value = values[0] if len(values) == 1 else values[0]

    def _set_attribute_value(self, instance: ObjectInstance, attr_path: str, value: str) -> None:
        """Set an attribute to a single value."""
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            part_inst = instance.parts.get(part_name)
            if part_inst:
                attr_inst = part_inst.attributes.get(attr_name)
                if attr_inst:
                    attr_inst.current_value = value

    def _update_snapshot_attribute(self, snapshot: WorldSnapshot, attr_path: str, values: List[str]) -> None:
        """
        Update an attribute value in a snapshot, preserving trend-based value sets.

        If the snapshot already has a value SET (from trend computation), we don't
        override it - the trend-based set is more accurate for future branching.
        """
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            if part_name in snapshot.object_state.parts:
                attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
                if attr:
                    # Only update if snapshot has single value (no trend-based set)
                    current_is_set = isinstance(attr.value, list)
                    if not current_is_set:
                        attr.value = values[0] if len(values) == 1 else values
                    # If snapshot already has a set (from trend), preserve it

    def _build_changes_list_from_raw(self, raw_changes: List[Any]) -> List[Dict[str, Any]]:
        """Convert raw effect changes to the serializable format.

        Filters out:
        - Info entries
        - Internal entries (starting with '[')
        - No-op changes where before == after
        """
        changes = []
        for change in raw_changes:
            if isinstance(change, dict):
                # Skip no-op changes
                if change.get("before") == change.get("after"):
                    continue
                # Skip internal entries
                attr = change.get("attribute", "")
                if attr.startswith("[") or change.get("kind") == "info":
                    continue
                changes.append(change)
            elif hasattr(change, "attribute") and hasattr(change, "before") and hasattr(change, "after"):
                # Skip no-op changes
                if change.before == change.after:
                    continue
                # Skip internal entries
                if change.attribute.startswith("[") or getattr(change, "kind", "value") == "info":
                    continue
                changes.append(
                    {
                        "attribute": change.attribute,
                        "before": change.before,
                        "after": change.after,
                        "kind": getattr(change, "kind", "value"),
                    }
                )
        return changes

    def _create_postcondition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> List[TreeNode]:
        """
        Create N+1 branches for postcondition: one for each if/elif case + else.

        When postcondition has if-elif-else structure checking an unknown attribute:
        - Each if/elif case gets its own branch with that specific value
        - The else branch gets remaining values as a set

        If parent_snapshot has a value SET for attr_path, we constrain branches
        to only those values.

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            attr_path: Path to the unknown attribute
            parent_snapshot: Optional parent snapshot (for constraining value sets)

        Returns:
            List of N+1 TreeNodes
        """
        # Get all branch options from action structure
        options = self._get_postcondition_branch_options(action, instance, attr_path)

        if not options:
            # No conditional effects, use linear execution
            return self._apply_action_linear(tree, instance, parent_node, action, parameters)

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
            )
            branches.append(node)

        return branches

    def _create_branch_success_node(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
    ) -> TreeNode:
        """Create a success branch node (precondition passed)."""
        # Clone instance with the constrained values
        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        # Add narrowing change if the value actually narrowed
        narrowing = self._compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes  # Put narrowing first

        # Capture the new state (pass parent snapshot for trend-based value set computation)
        new_snapshot = self._capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            parent_node.snapshot,
        )

        # Determine operator based on value count
        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]

        return TreeNode(
            id=tree.generate_node_id(),
            snapshot=new_snapshot,
            parent_id=parent_node.id,
            action_name=action.name,
            action_parameters=parameters,
            action_status=NodeStatus.OK.value,
            branch_condition=BranchCondition(
                attribute=attr_path,
                operator=operator,
                value=value,
                source="precondition",
                branch_type="success",
            ),
            changes=changes,
        )

    def _create_branch_fail_node(
        self,
        tree: SimulationTree,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
    ) -> TreeNode:
        """Create a fail branch node (precondition failed)."""
        # Capture snapshot with constrained values (state unchanged, but values narrowed)
        new_snapshot = self._snapshot_with_constrained_values(parent_node.snapshot, attr_path, values)

        operator = "in" if len(values) > 1 else "equals"
        value = values if len(values) > 1 else values[0]

        # Build detailed error message matching the engine's format
        error_msg = self._build_precondition_error(action, attr_path, values)

        # Include the narrowing as a change if the value actually changed
        changes = self._compute_narrowing_change(parent_node.snapshot, attr_path, values)

        return TreeNode(
            id=tree.generate_node_id(),
            snapshot=new_snapshot,
            parent_id=parent_node.id,
            action_name=action.name,
            action_parameters=parameters,
            action_status=NodeStatus.REJECTED.value,
            action_error=error_msg,
            branch_condition=BranchCondition(
                attribute=attr_path,
                operator=operator,
                value=value,
                source="precondition",
                branch_type="fail",
            ),
            changes=changes,
        )

    def _create_branch_case_node(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        value: Union[str, List[str]],
        branch_type: str,
        effects: Any,
    ) -> TreeNode:
        """Create a branch node for a postcondition case (if/elif/else)."""
        # Clone instance with the specific value(s)
        values = value if isinstance(value, list) else [value]
        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        # Apply the action
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        # Add narrowing change if the value actually narrowed
        narrowing = self._compute_narrowing_change(parent_node.snapshot, attr_path, values)
        changes = narrowing + changes  # Put narrowing first

        # Capture new state (pass parent snapshot for trend-based value set computation)
        new_snapshot = self._capture_snapshot_with_values(
            result.after if result.after else modified_instance,
            attr_path,
            values,
            parent_node.snapshot,
        )

        operator = "in" if isinstance(value, list) else "equals"

        return TreeNode(
            id=tree.generate_node_id(),
            snapshot=new_snapshot,
            parent_id=parent_node.id,
            action_name=action.name,
            action_parameters=parameters,
            action_status=NodeStatus.OK.value,
            branch_condition=BranchCondition(
                attribute=attr_path,
                operator=operator,
                value=value,
                source="postcondition",
                branch_type=branch_type,
            ),
            changes=changes,
        )

    def _clone_instance_with_values(
        self, instance: ObjectInstance, attr_path: str, values: List[str]
    ) -> ObjectInstance:
        """
        Clone an instance and set the attribute to specific value(s).

        For branching, we need to constrain the instance to specific values
        before applying the action.
        """
        # Deep copy the instance
        from copy import deepcopy

        new_instance = deepcopy(instance)

        # Set the attribute value
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            if part_name in new_instance.parts:
                attr_inst = new_instance.parts[part_name].attributes.get(attr_name)
                if attr_inst:
                    # Set to single value for action evaluation
                    attr_inst.current_value = values[0] if values else None
        elif len(parts) == 1:
            attr_inst = new_instance.global_attributes.get(parts[0])
            if attr_inst:
                attr_inst.current_value = values[0] if values else None

        return new_instance

    def _capture_snapshot_with_values(
        self,
        instance: ObjectInstance,
        attr_path: str,
        values: List[str],
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> WorldSnapshot:
        """
        Capture a snapshot, preserving trend-based value sets.

        The `values` parameter is used for branch condition tracking, but the
        snapshot's actual value is computed by `_capture_snapshot` which considers
        trends. If a trend produces a value SET, we preserve it rather than
        overriding with a single value.

        Only override the value if:
        - `_capture_snapshot` returned a single value (no active trend), OR
        - We need to constrain to multiple explicit values
        """
        snapshot = self._capture_snapshot(instance, parent_snapshot)

        # Check if _capture_snapshot already computed a value set from trend
        # If so, don't override it - the trend-based set is more accurate
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            if part_name in snapshot.object_state.parts:
                attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
                if attr:
                    # Only override if snapshot has single value AND we have multiple constraint values
                    # OR if snapshot has single value and we want a single value
                    current_is_set = isinstance(attr.value, list)
                    if not current_is_set:
                        # Snapshot has single value, can override with constraint
                        attr.value = values[0] if len(values) == 1 else values
                    # If snapshot already has a set (from trend), preserve it
        elif len(parts) == 1:
            attr = snapshot.object_state.global_attributes.get(parts[0])
            if attr:
                current_is_set = isinstance(attr.value, list)
                if not current_is_set:
                    attr.value = values[0] if len(values) == 1 else values

        return snapshot

    def _snapshot_with_constrained_values(
        self, snapshot: WorldSnapshot, attr_path: str, values: List[str]
    ) -> WorldSnapshot:
        """
        Create a copy of a snapshot with attribute values constrained.

        Used for fail branches where state doesn't change but values are narrowed.
        """
        from copy import deepcopy

        new_snapshot = deepcopy(snapshot)

        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            if part_name in new_snapshot.object_state.parts:
                attr = new_snapshot.object_state.parts[part_name].attributes.get(attr_name)
                if attr:
                    attr.value = values[0] if len(values) == 1 else values
        elif len(parts) == 1:
            attr = new_snapshot.object_state.global_attributes.get(parts[0])
            if attr:
                attr.value = values[0] if len(values) == 1 else values

        return new_snapshot

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
            snapshot=self._capture_snapshot(instance, parent_node.snapshot),
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

    def _capture_snapshot(
        self, obj_instance: ObjectInstance, parent_snapshot: Optional[WorldSnapshot] = None
    ) -> WorldSnapshot:
        """
        Capture the current object state as a WorldSnapshot.

        When an attribute has an active trend (not "none"), its value becomes a
        value SET representing all possible values the trend could produce.
        - trend "down" from "medium" → ["empty", "low", "medium"]
        - trend "up" from "low" → ["low", "medium", "high", "full"]

        Value sets are preserved from parent snapshot if the action only clears
        the trend without setting a new specific value.
        """
        parts: Dict[str, PartStateSnapshot] = {}

        for part_name, part_instance in obj_instance.parts.items():
            attrs: Dict[str, AttributeSnapshot] = {}
            for attr_name, attr_instance in part_instance.attributes.items():
                attr_path = f"{part_name}.{attr_name}"
                value = self._compute_value_with_trend(attr_instance, attr_path, parent_snapshot)
                attrs[attr_name] = AttributeSnapshot(
                    value=value,
                    trend=attr_instance.trend,
                    last_known_value=attr_instance.last_known_value,
                    last_trend_direction=attr_instance.last_trend_direction,
                    space_id=attr_instance.spec.space_id,
                )
            parts[part_name] = PartStateSnapshot(attributes=attrs)

        global_attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in obj_instance.global_attributes.items():
            value = self._compute_value_with_trend(attr_instance, attr_name, parent_snapshot)
            global_attrs[attr_name] = AttributeSnapshot(
                value=value,
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

    def _compute_value_with_trend(
        self, attr_instance, attr_path: str, parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Union[str, List[str]]:
        """
        Compute the value for an attribute, considering its trend and parent value set.

        - If the attribute has an active trend (up/down), returns a value set
        - If parent had a value set and this action didn't set a new concrete value,
          preserve the value set
        - Otherwise returns the single current value
        """
        current_value = attr_instance.current_value
        trend = attr_instance.trend
        space_id = attr_instance.spec.space_id

        # If there's an active trend, compute value set
        if trend and trend != "none" and current_value != "unknown":
            if space_id:
                value_set = self._compute_value_set_from_trend(current_value, trend, space_id)
                if len(value_set) > 1:
                    return value_set

        # If parent had a value set and current value matches the original,
        # preserve the value set (action only cleared trend, didn't set new value)
        if parent_snapshot:
            parent_value = parent_snapshot.get_attribute_value(attr_path)
            if isinstance(parent_value, list) and len(parent_value) > 1:
                # Check if current value is in the parent's value set
                # (meaning the action didn't set a specific new value)
                if current_value in parent_value or current_value == attr_instance.last_known_value:
                    return parent_value

        return current_value

    # =========================================================================
    # Utilities
    # =========================================================================

    def _parse_action_requests(self, actions: List[Union[ActionRequest, Dict[str, Any]]]) -> List[ActionRequest]:
        """Parse action list into ActionRequest objects."""
        return [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action) for action in actions
        ]

    def _apply_initial_values(self, instance: ObjectInstance, values: Dict[str, str]) -> None:
        """
        Apply initial value overrides to an object instance.

        Args:
            instance: Object instance to modify
            values: Dict mapping attribute paths to values
                    e.g., {"battery.level": "unknown", "switch.position": "on"}
        """
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
        """Build serializable changes list from DiffEntry objects.

        Filters out:
        - Info entries
        - Internal entries (starting with '[')
        - No-op changes where before == after
        """
        return [
            {
                "attribute": c.attribute,
                "before": c.before,
                "after": c.after,
                "kind": c.kind,
            }
            for c in changes
            if c.kind != "info" and not c.attribute.startswith("[") and c.before != c.after  # Filter out no-op changes
        ]

    def _build_precondition_error(self, action: Action, attr_path: str, actual_values: List[str]) -> str:
        """Build detailed precondition error message using shared utility."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.utils.error_formatting import format_precondition_error

        # Find the precondition that checks this attribute
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

        # Fallback if condition not found
        actual_str = actual_values[0] if len(actual_values) == 1 else "{" + ", ".join(actual_values) + "}"
        return f"Precondition failed: {attr_path} (actual: {actual_str})"

    def _compute_narrowing_change(
        self, parent_snapshot: WorldSnapshot, attr_path: str, new_values: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Compute the change entry for attribute value narrowing during branching.

        Only returns a change if the value actually narrowed (e.g., from value set to single value,
        or from 'unknown' to a specific value).

        Returns:
            List with single change dict, or empty list if no narrowing occurred.
        """
        # Get parent's value for this attribute
        parent_value = parent_snapshot.get_attribute_value(attr_path)

        # Format the new value
        if len(new_values) == 1:
            new_value = new_values[0]
        else:
            new_value = new_values  # Keep as list for value sets

        # Format the parent value for comparison
        if isinstance(parent_value, list):
            parent_display = parent_value
        else:
            parent_display = parent_value

        # Only include as change if values are different
        if parent_display != new_value:
            return [
                {
                    "attribute": attr_path,
                    "before": parent_display,
                    "after": new_value,
                    "kind": "value",
                }
            ]

        return []

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

    def __init__(
        self,
        node: TreeNode,
        instance: Optional[ObjectInstance],
        action: Optional[Action] = None,
    ):
        """
        Args:
            node: The node created for this action
            instance: Updated instance if action succeeded, None otherwise
            action: The action that was processed
        """
        self.node = node
        self.instance = instance
        self.action = action


__all__ = ["TreeSimulationRunner", "ActionResult"]
