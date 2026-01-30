"""
Shared fixtures and helpers for tree simulation tests.
"""

from typing import Dict, List, Optional, Tuple

import pytest

from simulator.cli.paths import kb_actions_path, kb_objects_path, kb_spaces_path
from simulator.core.registries import RegistryManager
from simulator.core.tree import TreeSimulationRunner
from simulator.core.tree.models import SimulationTree, TreeNode
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _load_test_registries() -> RegistryManager:
    """Load all registries for testing."""
    rm = RegistryManager()
    load_spaces(kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(kb_objects_path(None), rm)
    load_actions(kb_actions_path(None), rm)
    return rm


@pytest.fixture(scope="module")
def registry_manager() -> RegistryManager:
    """Load registries once for all tests in the module."""
    return _load_test_registries()


@pytest.fixture
def runner(registry_manager: RegistryManager) -> TreeSimulationRunner:
    """Create a TreeSimulationRunner for testing."""
    return TreeSimulationRunner(registry_manager)


# =============================================================================
# Common Initial Values Fixtures
# =============================================================================


@pytest.fixture
def slot_machine_unknown() -> Dict[str, str]:
    """Initial values for slot machine with all reels unknown."""
    return {
        "reel1.symbol": "unknown",
        "reel2.symbol": "unknown",
        "reel3.symbol": "unknown",
    }


@pytest.fixture
def coffee_machine_unknown() -> Dict[str, str]:
    """Initial values for coffee machine with all attributes unknown."""
    return {
        "water_tank.level": "unknown",
        "bean_hopper.amount": "unknown",
        "heater.temperature": "unknown",
    }


@pytest.fixture
def flashlight_unknown() -> Dict[str, str]:
    """Initial values for flashlight with battery unknown."""
    return {"battery.level": "unknown"}


# =============================================================================
# Helper Functions
# =============================================================================


def get_branches(tree: SimulationTree, root_id: str = "state0") -> Tuple[List[TreeNode], List[TreeNode]]:
    """Get success and fail branches from tree.

    Args:
        tree: The simulation tree
        root_id: ID of the parent node to check

    Returns:
        Tuple of (success_nodes, fail_nodes)
    """
    root = tree.nodes[root_id]
    success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
    fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]
    return success, fail


def get_reel_values(node: TreeNode) -> Dict[str, Optional[str]]:
    """Get all reel symbol values from a slot machine node.

    Args:
        node: TreeNode to extract values from

    Returns:
        Dict mapping reel name to symbol value
    """
    return {
        "reel1": node.snapshot.get_attribute_value("reel1.symbol"),
        "reel2": node.snapshot.get_attribute_value("reel2.symbol"),
        "reel3": node.snapshot.get_attribute_value("reel3.symbol"),
    }


def run_simulation(
    runner: TreeSimulationRunner,
    object_type: str,
    action_name: str,
    initial_values: Optional[Dict[str, str]] = None,
    simulation_id: Optional[str] = None,
) -> SimulationTree:
    """Helper to run a single-action simulation.

    Args:
        runner: TreeSimulationRunner instance
        object_type: Type of object (e.g., "flashlight", "slot_machine")
        action_name: Name of action to run
        initial_values: Optional dict of attr_path -> value
        simulation_id: Optional simulation ID

    Returns:
        SimulationTree result
    """
    return runner.run(
        object_type,
        [{"name": action_name, "parameters": {}}],
        simulation_id=simulation_id or f"test_{action_name}",
        initial_values=initial_values,
    )


def assert_branch_condition(
    node: TreeNode,
    compound_type: Optional[str] = None,
    sub_count: Optional[int] = None,
    branch_type: Optional[str] = None,
) -> None:
    """Assert properties of a node's branch condition.

    Args:
        node: TreeNode to check
        compound_type: Expected compound_type (e.g., "and", "or") or None
        sub_count: Expected number of sub_conditions
        branch_type: Expected branch_type (e.g., "success", "fail", "if", "else")
    """
    bc = node.branch_condition
    assert bc is not None, "Node has no branch condition"

    if compound_type is not None:
        assert bc.compound_type == compound_type, f"Expected compound_type={compound_type}, got {bc.compound_type}"

    if sub_count is not None:
        assert bc.sub_conditions is not None, "Expected sub_conditions but got None"
        assert len(bc.sub_conditions) == sub_count, f"Expected {sub_count} sub_conditions, got {len(bc.sub_conditions)}"

    if branch_type is not None:
        assert bc.branch_type == branch_type, f"Expected branch_type={branch_type}, got {bc.branch_type}"
