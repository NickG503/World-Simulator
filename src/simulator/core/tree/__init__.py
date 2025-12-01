"""
Tree-based simulation module.

This module provides the core data structures and runner for tree-based
simulation execution. The tree structure supports:

Phase 1 (Current): Linear execution with all values known
Phase 2 (Future): Branching on unknown attributes

Main Components:
- WorldSnapshot: Immutable capture of world state at a point in time
- TreeNode: A node in the simulation tree (world state + action info)
- BranchCondition: Describes what condition led to a branch
- SimulationTree: Complete tree structure with all nodes
- TreeSimulationRunner: Executes simulations building the tree

Example:
    from simulator.core.tree import TreeSimulationRunner, SimulationTree

    runner = TreeSimulationRunner(registry_manager)
    tree = runner.run(
        object_type="flashlight",
        actions=[{"name": "turn_on"}, {"name": "turn_off"}],
        simulation_id="demo"
    )

    # Access nodes
    root = tree.root
    for node_id in tree.current_path:
        node = tree.get_node(node_id)
        print(node.describe())

    # Save to YAML
    runner.save_tree_to_yaml(tree, "output.yaml")
"""

from simulator.core.tree.models import (
    BranchCondition,
    BranchSource,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.tree.tree_runner import ActionResult, TreeSimulationRunner

__all__ = [
    # Models
    "WorldSnapshot",
    "BranchCondition",
    "BranchSource",
    "NodeStatus",
    "TreeNode",
    "SimulationTree",
    # Runner
    "TreeSimulationRunner",
    "ActionResult",
]
