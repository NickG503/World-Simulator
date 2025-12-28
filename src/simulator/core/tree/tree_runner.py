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
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union

import yaml

from simulator.core.actions.action import Action
from simulator.core.attributes import AttributePath
from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.simulation_runner import ActionRequest
from simulator.core.tree.models import (
    BranchCondition,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.tree.node_factory import (
    compute_narrowing_change,
    create_error_node,
    create_or_merge_node,
    create_root_node,
)
from simulator.core.tree.snapshot_utils import (
    capture_snapshot,
    capture_snapshot_with_values,
    get_all_space_values,
    get_attribute_space_id,
    snapshot_with_constrained_values,
)

if TYPE_CHECKING:
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.actions.conditions.base import Condition
    from simulator.core.actions.conditions.logical_conditions import (
        AndCondition,
        OrCondition,
    )

logger = logging.getLogger(__name__)


class TreeSimulationRunner:
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
        root_snapshot = capture_snapshot(obj_instance, self.registry_manager)
        root_node = create_root_node(tree, root_snapshot)
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

            # Create a fresh state cache for this layer (DAG deduplication)
            # Key: state hash, Value: (node, instance) tuple
            layer_state_cache: Dict[str, Tuple[TreeNode, ObjectInstance]] = {}

            # Track which nodes we've already added to new_leaves (avoid duplicates)
            seen_node_ids: set = set()

            for current_node, current_instance in leaves:
                # Process action on this branch
                results = self._process_action_multi(
                    tree=tree,
                    instance=current_instance,
                    parent_node=current_node,
                    action_name=request.name,
                    parameters=request.parameters,
                    verbose=verbose,
                    layer_state_cache=layer_state_cache,
                )

                # Each result becomes a new leaf (but deduplicate merged nodes)
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
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> "ActionResult":
        """Process action, creating branches for unknown attributes."""
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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> List[TreeNode]:
        """Apply action linearly (no branching), returning single node.

        Returns:
            List containing single TreeNode (may be existing node if deduplicated)
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        result = self.engine.apply_action(instance, action, parameters)

        # Build changes list
        changes = self._build_changes_list(result.changes)

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
        for condition in action.preconditions:
            unknown = self._find_unknown_in_condition(condition, instance, parent_snapshot)
            if unknown:
                return unknown
        return None

    def _find_unknown_in_condition(
        self,
        condition,
        instance: ObjectInstance,
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> Optional[str]:
        """Recursively find unknown attributes in a condition (including compound)."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

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
        elif isinstance(condition, (AndCondition, OrCondition)):
            # Check all sub-conditions
            for sub_cond in condition.conditions:
                unknown = self._find_unknown_in_condition(sub_cond, instance, parent_snapshot)
                if unknown:
                    return unknown
        return None

    def _get_unknown_attributes_in_condition(
        self,
        condition,
        instance: ObjectInstance,
        parent_snapshot: Optional[WorldSnapshot] = None,
    ) -> List[Tuple[str, "AttributeCondition"]]:
        """Get ALL unknown attributes in a condition (for compound conditions).

        Returns list of (attr_path, condition) tuples for all unknown attributes.
        """
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        unknowns: List[Tuple[str, AttributeCondition]] = []

        if isinstance(condition, AttributeCondition):
            try:
                ai = condition.target.resolve(instance)
                attr_path = condition.target.to_string()

                is_unknown = ai.current_value == "unknown"
                if not is_unknown and parent_snapshot:
                    snapshot_value = parent_snapshot.get_attribute_value(attr_path)
                    is_unknown = isinstance(snapshot_value, list) and len(snapshot_value) > 1

                if is_unknown:
                    unknowns.append((attr_path, condition))
            except Exception:
                pass
        elif isinstance(condition, (AndCondition, OrCondition)):
            for sub_cond in condition.conditions:
                unknowns.extend(self._get_unknown_attributes_in_condition(sub_cond, instance, parent_snapshot))

        return unknowns

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
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        for effect in action.effects:
            if isinstance(effect, ConditionalEffect):
                unknown = self._find_unknown_in_condition(effect.condition, instance, parent_snapshot)
                if unknown:
                    return unknown
        return None

    def _has_compound_postcondition(
        self, action: Action, instance: ObjectInstance, parent_snapshot: Optional[WorldSnapshot] = None
    ) -> Optional[Tuple[Condition, List[Any], List[Tuple[str, "AttributeCondition"]]]]:
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

    def _get_precondition_condition(self, action: Action):
        """Get the first precondition condition that checks an attribute (or compound)."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        for condition in action.preconditions:
            if isinstance(condition, (AttributeCondition, AndCondition, OrCondition)):
                return condition
        return None

    def _evaluate_condition_for_value(self, condition, value: str, instance: Optional[ObjectInstance] = None) -> bool:
        """
        Check if a specific value would pass a condition.

        Args:
            condition: The condition to evaluate
            value: The value to test
            instance: Optional object instance for resolving qualitative spaces

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
        elif condition.operator in ("gt", "gte", "lt", "lte"):
            # For qualitative spaces, compare by order using the space
            if instance is None:
                return False
            try:
                ai = condition.target.resolve(instance)
                space = self.registry_manager.spaces.get(ai.spec.space_id)
                if space:
                    satisfying_values = space.get_values_for_comparison(str(condition.value), condition.operator)
                    return value in satisfying_values
            except (ValueError, AttributeError):
                pass
            return False
        return True

    # =========================================================================
    # Phase 2: Branching Methods
    # =========================================================================

    def _create_combined_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        precond_attr: str,
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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

        For AND conditions with multiple unknown attributes:
        - Success branch constrains ALL attributes to satisfying values
        - Fail branch keeps original state (action rejected)

        Uses layer_state_cache for DAG deduplication.

        Args:
            tree: Simulation tree
            instance: Current object instance
            parent_node: Parent node
            action: Action being applied
            parameters: Action parameters
            precond_attr: Attribute path checked in precondition (first unknown)
            postcond_attr: Attribute path checked in postcondition (may be None or same)
            layer_state_cache: Optional cache for deduplication

        Returns:
            List of branches: 1 fail + N success sub-branches
        """
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if layer_state_cache is None:
            layer_state_cache = {}
        condition = self._get_precondition_condition(action)

        if not condition:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Handle AND conditions with multiple attributes
        if isinstance(condition, AndCondition):
            return self._create_and_condition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )

        # Handle OR conditions (creates multiple success branches)
        if isinstance(condition, OrCondition):
            return self._create_or_condition_branches(
                tree=tree,
                instance=instance,
                parent_node=parent_node,
                action=action,
                parameters=parameters,
                condition=condition,
                postcond_attr=postcond_attr,
                layer_state_cache=layer_state_cache,
            )

        # Simple AttributeCondition - original logic
        space_id = get_attribute_space_id(instance, precond_attr)

        if not space_id:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Get possible values from parent snapshot or space
        possible_values: List[str] = []
        if parent_node and parent_node.snapshot:
            snapshot_value = parent_node.snapshot.get_attribute_value(precond_attr)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)

        if not possible_values:
            possible_values = get_all_space_values(space_id, self.registry_manager)

        if not possible_values:
            return self._apply_action_linear(tree, instance, parent_node, action, parameters, layer_state_cache)

        # Partition into passing and failing values
        pass_values = [v for v in possible_values if self._evaluate_condition_for_value(condition, v, instance)]
        fail_values = [v for v in possible_values if not self._evaluate_condition_for_value(condition, v, instance)]

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
                    layer_state_cache=layer_state_cache,
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
                    layer_state_cache=layer_state_cache,
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
                layer_state_cache=layer_state_cache,
            )
            branches.append(fail_node)

        return branches

    def _create_and_condition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "AndCondition",
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        satisfying = self._get_satisfying_values_for_and_condition(condition, instance, parent_node.snapshot)

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
                    modified_instance = self._clone_instance_with_multi_values(instance, satisfying)
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
                modified_instance = self._clone_instance_with_multi_values(instance, satisfying)
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

    def _create_and_postcond_branch(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_values: Dict[str, List[str]],
        postcond_attr: str,
        postcond_values: List[str],
        branch_type: str,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> TreeNode:
        """Create a branch for AND precondition with postcondition constraint.

        Combines precondition AND constraints with postcondition if/elif/else case.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with all constrained values
        modified_instance = self._clone_instance_with_multi_values(instance, attr_values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        # Add narrowing changes for all constrained attributes
        for attr_path, values in attr_values.items():
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes = narrowing + changes

        # Capture new state with all constrained values
        result_instance = result.after if result.after else modified_instance
        new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        # Update snapshot with constrained value sets
        for attr_path, values in attr_values.items():
            self._update_snapshot_attribute(new_snapshot, attr_path, values)

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

    def _create_and_success_branch(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_values: Dict[str, List[str]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> TreeNode:
        """Create a success branch for AND condition with multiple constrained attributes."""
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with all constrained values
        modified_instance = self._clone_instance_with_multi_values(instance, attr_values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

        # Add narrowing changes for all constrained attributes
        for attr_path, values in attr_values.items():
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
            changes = narrowing + changes

        # Capture new state with all constrained values
        result_instance = result.after if result.after else modified_instance
        new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

        # Update snapshot with constrained value sets
        for attr_path, values in attr_values.items():
            self._update_snapshot_attribute(new_snapshot, attr_path, values)

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

    def _create_and_fail_branch(
        self,
        tree: SimulationTree,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "AndCondition",
        instance: ObjectInstance,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        satisfying = self._get_satisfying_values_for_and_condition(condition, instance, parent_node.snapshot)

        # For each attribute, create a fail branch where THAT attribute fails
        # and other attributes remain unknown
        for attr_path, passing_values in satisfying.items():
            # Get possible values for this attribute
            all_values, is_known = self._get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None
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
                    other_values, _ = self._get_possible_values_for_attribute(
                        other_attr, instance, parent_node.snapshot if parent_node else None
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
        condition: Condition,
        instance: ObjectInstance,
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
            possible_values, is_known = self._get_possible_values_for_attribute(attr_path, instance, parent_snapshot)

            if not possible_values:
                return []

            if is_known:
                if self._evaluate_condition_for_value(condition, possible_values[0], instance):
                    # Known value satisfies - can't fail
                    return []
                else:
                    # Known value fails - use it
                    return [{attr_path: possible_values}]

            satisfying = [v for v in possible_values if self._evaluate_condition_for_value(condition, v, instance)]
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

    def _create_or_fail_branches(
        self,
        tree: SimulationTree,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "OrCondition",
        instance: ObjectInstance,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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

    def _create_or_condition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "OrCondition",
        postcond_attr: Optional[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
                possible_values, is_known_value = self._get_possible_values_for_attribute(
                    attr_path, instance, parent_node.snapshot if parent_node else None
                )

                if not possible_values:
                    continue

                # Get satisfying values for this condition
                satisfying = [v for v in possible_values if self._evaluate_condition_for_value(attr_cond, v, instance)]

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
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        changes = self._build_changes_list(raw_changes)

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

    def _set_attribute_value(self, instance: ObjectInstance, attr_path: str, value: str) -> None:
        """Set an attribute to a single value."""
        AttributePath.parse(attr_path).set_value_in_instance(instance, value)

    def _update_snapshot_attribute(self, snapshot: WorldSnapshot, attr_path: str, values: List[str]) -> None:
        """Update snapshot attribute, preserving existing value sets from trends."""
        attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
        if attr and not isinstance(attr.value, list):
            attr.value = values[0] if len(values) == 1 else values

    def _normalize_change(self, change: Any) -> Optional[Dict[str, Any]]:
        """Normalize a change (dict or object) to dict format, filtering invalid entries."""
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

        # Filter: no-ops, info entries, internal entries
        if before == after or kind == "info" or attr.startswith("["):
            return None

        return {"attribute": attr, "before": before, "after": after, "kind": kind}

    def _create_postcondition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        parent_snapshot: Optional[WorldSnapshot] = None,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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

    def _create_compound_postcondition_branches(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: Condition,
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "AndCondition",
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        satisfying = self._get_satisfying_values_for_and_condition(condition, instance, parent_node.snapshot)

        # THEN branch: all attributes constrained to satisfying values
        if satisfying and all(v for v in satisfying.values()):
            # Clone instance with all constrained values
            modified_instance = self._clone_instance_with_multi_values(instance, satisfying)

            # Apply action effects
            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = self._build_changes_list(result.changes)

            # Add narrowing changes
            for attr_path, values in satisfying.items():
                narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, values)
                changes = narrowing + changes

            result_instance = result.after if result.after else modified_instance
            new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

            # Note: Do NOT call _update_snapshot_attribute here for THEN branches
            # The effect results are already in the snapshot via capture_snapshot
            # We only need to set constraints for attributes NOT affected by effects

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
            possible_values, _ = self._get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None
            )
            if not possible_values:
                continue

            # Get satisfying values for this sub-condition
            satisfying_for_attr = [
                v for v in possible_values if self._evaluate_condition_for_value(sub_cond, v, instance)
            ]

            # Complement = values that FAIL this condition
            complement = [v for v in possible_values if v not in satisfying_for_attr]

            if not complement:
                continue  # This condition can't fail

            # Apply action WITHOUT the conditional effects (else path)
            modified_instance = self._clone_instance_with_multi_values(instance, {attr_path: complement})
            result = self.engine.apply_action(modified_instance, action, parameters)

            # Get attributes actually modified by EFFECTS (before adding narrowing)
            effect_changes = self._build_changes_list(result.changes)
            effect_changed_attrs = {c.get("attribute") for c in effect_changes if c.get("kind") == "value"}

            # Build combined changes with narrowing
            changes = list(effect_changes)
            narrowing = compute_narrowing_change(parent_node.snapshot, attr_path, complement)
            changes = narrowing + changes

            result_instance = result.after if result.after else modified_instance
            new_snapshot = capture_snapshot(result_instance, self.registry_manager, parent_node.snapshot)

            # Only update snapshot if this attr was NOT modified by effects
            if attr_path not in effect_changed_attrs:
                self._update_snapshot_attribute(new_snapshot, attr_path, complement)

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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        condition: "OrCondition",
        effects: List[Any],
        unknowns: List[Tuple[str, "AttributeCondition"]],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
            possible_values, _ = self._get_possible_values_for_attribute(
                attr_path, instance, parent_node.snapshot if parent_node else None
            )
            if not possible_values:
                continue

            # Get satisfying values for this sub-condition
            satisfying = [v for v in possible_values if self._evaluate_condition_for_value(sub_cond, v, instance)]

            if not satisfying:
                continue

            # Apply action WITH effects (this disjunct is true)
            modified_instance = self._clone_instance_with_multi_values(instance, {attr_path: satisfying})
            result = self.engine.apply_action(modified_instance, action, parameters)
            changes = self._build_changes_list(result.changes)

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
                possible_values, _ = self._get_possible_values_for_attribute(attr_path, instance, parent_snapshot)
                if not possible_values:
                    continue

                satisfying = [v for v in possible_values if self._evaluate_condition_for_value(sub_cond, v, instance)]
                complement = [v for v in possible_values if v not in satisfying]

                if complement:
                    complement_values[attr_path] = complement

            if complement_values:
                # All attributes are constrained to their complements
                modified_instance = self._clone_instance_with_multi_values(instance, complement_values)
                result = self.engine.apply_action(modified_instance, action, parameters)

                # Get attributes actually modified by EFFECTS
                effect_changes = self._build_changes_list(result.changes)
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
                        self._update_snapshot_attribute(new_snapshot, attr_path, values)

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

    def _create_branch_success_node(
        self,
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> TreeNode:
        """Create a success branch node (precondition passed).

        Uses layer_state_cache for DAG deduplication.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with the constrained values
        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        # Apply the action to get effects
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

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
        tree: SimulationTree,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        values: List[str],
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
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
        error_msg = self._build_precondition_error(action, attr_path, values)

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
        tree: SimulationTree,
        instance: ObjectInstance,
        parent_node: TreeNode,
        action: Action,
        parameters: Dict[str, str],
        attr_path: str,
        value: Union[str, List[str]],
        branch_type: str,
        effects: Any,
        layer_state_cache: Optional[Dict[str, Tuple[TreeNode, ObjectInstance]]] = None,
    ) -> TreeNode:
        """Create a branch node for a postcondition case (if/elif/else).

        Uses layer_state_cache for DAG deduplication.
        """
        if layer_state_cache is None:
            layer_state_cache = {}

        # Clone instance with the specific value(s)
        values = value if isinstance(value, list) else [value]
        modified_instance = self._clone_instance_with_values(instance, attr_path, values)

        # Apply the action
        result = self.engine.apply_action(modified_instance, action, parameters)
        changes = self._build_changes_list(result.changes)

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

    def _clone_instance_with_values(
        self, instance: ObjectInstance, attr_path: str, values: List[str]
    ) -> ObjectInstance:
        """Clone an instance and constrain an attribute to specific value(s)."""
        new_instance = instance.deep_copy()
        if values:
            AttributePath.parse(attr_path).set_value_in_instance(new_instance, values[0])
        return new_instance

    def _clone_instance_with_multi_values(
        self, instance: ObjectInstance, attr_values: Dict[str, List[str]]
    ) -> ObjectInstance:
        """Clone an instance and constrain multiple attributes to specific values.

        Args:
            instance: Original instance to clone
            attr_values: Dict mapping attr_path -> list of possible values

        Returns:
            Cloned instance with first value set for each attribute
        """
        new_instance = instance.deep_copy()
        for attr_path, values in attr_values.items():
            if values:
                AttributePath.parse(attr_path).set_value_in_instance(new_instance, values[0])
        return new_instance

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

    def _create_demorgan_branch_condition(
        self,
        condition: Condition,
        instance: ObjectInstance,
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
            possible_values, is_known = self._get_possible_values_for_attribute(attr_path, instance, parent_snapshot)

            if not possible_values:
                return None

            # If known, check if it satisfies
            if is_known:
                if self._evaluate_condition_for_value(condition, possible_values[0], instance):
                    # Known value satisfies - can't fail
                    return None
                else:
                    # Known value fails - use it
                    return self._create_simple_branch_condition(attr_path, possible_values, source, branch_type)

            # Get complement (values that FAIL)
            satisfying = [v for v in possible_values if self._evaluate_condition_for_value(condition, v, instance)]
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

    def _get_possible_values_for_attribute(
        self,
        attr_path: str,
        instance: ObjectInstance,
        parent_snapshot: Optional[WorldSnapshot],
    ) -> Tuple[List[str], bool]:
        """Get possible values for an attribute from snapshot or space.

        Returns:
            Tuple of (possible_values, is_known_value)
            - possible_values: List of possible values
            - is_known_value: True if the value is definitively known (single value)
        """
        space_id = get_attribute_space_id(instance, attr_path)
        if not space_id:
            return [], False

        possible_values: List[str] = []
        is_known_value = False

        if parent_snapshot:
            snapshot_value = parent_snapshot.get_attribute_value(attr_path)
            if isinstance(snapshot_value, list):
                possible_values = list(snapshot_value)
            elif isinstance(snapshot_value, str) and snapshot_value != "unknown":
                # Known value
                possible_values = [snapshot_value]
                is_known_value = True

        if not possible_values:
            possible_values = get_all_space_values(space_id, self.registry_manager)

        return possible_values, is_known_value

    def _get_satisfying_values_for_condition(
        self,
        condition: Condition,
        instance: ObjectInstance,
        parent_snapshot: Optional[WorldSnapshot],
    ) -> Dict[str, List[str]]:
        """Get satisfying values for each attribute in any condition (simple or compound).

        Recursively handles nested AND/OR conditions by flattening to AttributeConditions.

        Args:
            condition: Any condition (AttributeCondition, AndCondition, OrCondition)
            instance: Object instance for space resolution
            parent_snapshot: Parent snapshot for value sets

        Returns:
            Dict mapping attr_path -> list of satisfying values
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        result: Dict[str, List[str]] = {}

        # Get all attribute conditions (flattened from any nested structure)
        if isinstance(condition, AttributeCondition):
            attr_conditions = [condition]
        elif isinstance(condition, (AndCondition, OrCondition)):
            attr_conditions = condition.get_attribute_conditions()
        else:
            return result

        for sub_cond in attr_conditions:
            attr_path = sub_cond.target.to_string()
            possible_values, _ = self._get_possible_values_for_attribute(attr_path, instance, parent_snapshot)

            if not possible_values:
                continue

            # Filter to values that satisfy this sub-condition
            satisfying = [v for v in possible_values if self._evaluate_condition_for_value(sub_cond, v, instance)]

            if attr_path in result:
                # Intersect with existing values for this attribute
                result[attr_path] = [v for v in result[attr_path] if v in satisfying]
            else:
                result[attr_path] = satisfying

        return result

    def _get_satisfying_values_for_and_condition(
        self,
        condition: "AndCondition",
        instance: ObjectInstance,
        parent_snapshot: Optional[WorldSnapshot],
    ) -> Dict[str, List[str]]:
        """Get satisfying values for each attribute in an AND condition.

        For AND conditions, we need to find values that satisfy each sub-condition.
        """
        return self._get_satisfying_values_for_condition(condition, instance, parent_snapshot)

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
        """Build serializable changes list, filtering info/internal/no-op entries."""
        result = []
        for c in changes:
            normalized = self._normalize_change(c)
            if normalized:
                result.append(normalized)
        return result

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


@dataclass
class ActionResult:
    """Result of processing an action."""

    node: TreeNode
    instance: Optional[ObjectInstance] = None
    action: Optional[Action] = None


__all__ = ["TreeSimulationRunner", "ActionResult"]
