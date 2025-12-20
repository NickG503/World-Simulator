"""
Tree-based simulation module.

Provides data structures and runner for tree/DAG simulation with branching on
unknown values.

Components:
- WorldSnapshot: Immutable capture of world state
- TreeNode: Node in the simulation DAG
- BranchCondition: What condition led to a branch
- SimulationTree: Complete DAG structure
- TreeSimulationRunner: Executes simulations

Example:
    from simulator.core.tree import TreeSimulationRunner, SimulationTree

    runner = TreeSimulationRunner(registry_manager)
    tree = runner.run(
        object_type="flashlight",
        actions=[{"name": "turn_on"}],
        simulation_id="demo"
    )
    runner.save_tree_to_yaml(tree, "output.yaml")
"""

from simulator.core.tree.models import (
    BranchCondition,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.tree.tree_runner import ActionResult, TreeSimulationRunner

__all__ = [
    "WorldSnapshot",
    "BranchCondition",
    "NodeStatus",
    "TreeNode",
    "SimulationTree",
    "TreeSimulationRunner",
    "ActionResult",
]
