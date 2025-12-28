"""
Tests for tree simulation data models.

Tests cover:
- WorldSnapshot
- TreeNode
- BranchCondition
- SimulationTree
"""

from simulator.core.simulation_runner import ObjectStateSnapshot
from simulator.core.tree.models import (
    BranchCondition,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)


class TestWorldSnapshot:
    """Tests for WorldSnapshot model."""

    def test_world_snapshot_creation(self):
        """WorldSnapshot can be created with object state."""
        obj_state = ObjectStateSnapshot(
            type="test_object",
            parts={},
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        assert snapshot.object_state.type == "test_object"
        assert snapshot.timestamp  # Should have default timestamp

    def test_world_snapshot_timestamp_format(self):
        """Timestamp should be in YYYY-MM-DD format."""
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        # Should match YYYY-MM-DD format
        import re

        assert re.match(r"\d{4}-\d{2}-\d{2}", snapshot.timestamp)


class TestTreeNode:
    """Tests for TreeNode model."""

    def test_tree_node_creation(self):
        """TreeNode can be created with required fields."""
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        node = TreeNode(
            id="state0",
            snapshot=snapshot,
        )

        assert node.id == "state0"
        assert node.parent_id is None
        assert node.children_ids == []
        assert node.action_name is None
        assert node.action_status == "ok"

    def test_tree_node_with_action(self):
        """TreeNode tracks action information."""
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        node = TreeNode(
            id="state1",
            snapshot=snapshot,
            parent_ids=["state0"],
            action_name="turn_on",
            action_parameters={"level": "high"},
            action_status="ok",
        )

        assert node.action_name == "turn_on"
        assert node.action_parameters == {"level": "high"}
        assert node.parent_id == "state0"  # backward-compatible property


class TestBranchCondition:
    """Tests for BranchCondition model."""

    def test_branch_condition_creation(self):
        """BranchCondition stores condition information."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="equals",
            value="high",
            source="precondition",
        )

        assert cond.attribute == "battery.level"
        assert cond.operator == "equals"
        assert cond.value == "high"
        assert cond.source == "precondition"


class TestSimulationTree:
    """Tests for SimulationTree model."""

    def test_simulation_tree_creation(self):
        """SimulationTree can be created with root node."""
        obj_state = ObjectStateSnapshot(type="flashlight", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)
        root = TreeNode(id="state0", snapshot=snapshot)

        tree = SimulationTree(
            simulation_id="test_sim",
            object_type="flashlight",
            object_name="flashlight",
            root_id="state0",
            nodes={"state0": root},
            current_path=["state0"],
        )

        assert tree.simulation_id == "test_sim"
        assert tree.object_type == "flashlight"
        assert tree.root_id == "state0"
        assert len(tree.nodes) == 1
        assert tree.current_path == ["state0"]
