"""
Tree-based simulation runner.

Executes simulations building a tree/DAG structure where nodes represent
world states and edges represent action transitions. Supports branching
on unknown attributes and merging of equivalent states.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import yaml

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.simulation_runner import ActionRequest
from simulator.core.tree.mixins import (
    ActionProcessingMixin,
    BranchCreationMixin,
    DeMorganBranchingMixin,
    PostconditionBranchingMixin,
    PreconditionBranchingMixin,
)
from simulator.core.tree.models import SimulationTree, TreeNode
from simulator.core.tree.node_factory import create_root_node
from simulator.core.tree.snapshot_utils import capture_snapshot

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TreeSimulationRunner(
    ActionProcessingMixin,
    PreconditionBranchingMixin,
    PostconditionBranchingMixin,
    DeMorganBranchingMixin,
    BranchCreationMixin,
):
    """Executes simulations building a tree/DAG structure with branching support."""

    def __init__(self, registry_manager: RegistryManager):
        from simulator.core.engine.transition_engine import TransitionEngine

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


# Re-export ActionResult from action_processing mixin for backward compatibility
from simulator.core.tree.mixins.action_processing import ActionResult

__all__ = ["TreeSimulationRunner", "ActionResult"]
