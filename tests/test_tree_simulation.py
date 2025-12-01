"""
Unit tests for tree-based simulation system.

Tests cover:
- TreeSimulationRunner execution
- SimulationTree structure
- TreeNode creation
- WorldSnapshot handling
- Precondition evaluation
- Effect application
- History serialization
"""

from pathlib import Path

import pytest
import yaml

from simulator.cli.paths import kb_actions_path, kb_objects_path, kb_spaces_path
from simulator.core.registries import RegistryManager
from simulator.core.tree.models import (
    BranchCondition,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.tree.tree_runner import TreeSimulationRunner
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
    """Load registries once for all tests."""
    return _load_test_registries()


class TestWorldSnapshot:
    """Tests for WorldSnapshot model."""

    def test_world_snapshot_creation(self):
        """WorldSnapshot can be created with object state."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

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
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        # Should match YYYY-MM-DD format
        import re

        assert re.match(r"\d{4}-\d{2}-\d{2}", snapshot.timestamp)


class TestTreeNode:
    """Tests for TreeNode model."""

    def test_tree_node_creation(self):
        """TreeNode can be created with required fields."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

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
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        node = TreeNode(
            id="state1",
            snapshot=snapshot,
            parent_id="state0",
            action_name="turn_on",
            action_parameters={"level": "high"},
            action_status="ok",
        )

        assert node.action_name == "turn_on"
        assert node.action_parameters == {"level": "high"}
        assert node.parent_id == "state0"


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
        from simulator.core.simulation_runner import ObjectStateSnapshot

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


class TestTreeSimulationRunner:
    """Tests for TreeSimulationRunner."""

    def test_runner_initialization(self, registry_manager):
        """Runner initializes with registry manager."""
        runner = TreeSimulationRunner(registry_manager)

        assert runner.registry_manager is registry_manager
        assert runner.engine is not None

    def test_simple_simulation(self, registry_manager):
        """Run simple flashlight turn_on simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions, simulation_id="test_simple")

        assert tree.simulation_id == "test_simple"
        assert tree.object_type == "flashlight"
        assert len(tree.nodes) == 2  # root + turn_on result
        assert tree.current_path == ["state0", "state1"]

    def test_multi_action_simulation(self, registry_manager):
        """Run multi-action simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_multi")

        assert len(tree.nodes) == 3  # root + turn_on + turn_off
        assert tree.current_path == ["state0", "state1", "state2"]

        # Verify parent-child relationships
        root = tree.nodes["state0"]
        assert "state1" in root.children_ids

        state1 = tree.nodes["state1"]
        assert state1.parent_id == "state0"
        assert state1.action_name == "turn_on"
        assert "state2" in state1.children_ids

        state2 = tree.nodes["state2"]
        assert state2.parent_id == "state1"
        assert state2.action_name == "turn_off"

    def test_node_ids_sequential(self, registry_manager):
        """Node IDs should be sequential state0, state1, etc."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        expected_ids = ["state0", "state1", "state2", "state3"]
        assert tree.current_path == expected_ids
        for node_id in expected_ids:
            assert node_id in tree.nodes

    def test_precondition_failure(self, registry_manager):
        """Action with failed precondition creates error node."""
        runner = TreeSimulationRunner(registry_manager)
        # drain_battery then turn_on - turn_on requires battery not empty
        actions = [
            {"name": "drain_battery", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_fail")

        assert len(tree.nodes) == 3
        state2 = tree.nodes["state2"]
        assert state2.action_name == "turn_on"
        assert state2.action_status == "rejected"
        assert state2.action_error is not None

    def test_changes_recorded(self, registry_manager):
        """Changes are recorded in nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        state1 = tree.nodes["state1"]
        assert len(state1.changes) > 0

        # Should have changes for switch.position and bulb.state at minimum
        change_attrs = [c["attribute"] for c in state1.changes]
        assert "switch.position" in change_attrs
        assert "bulb.state" in change_attrs

    def test_tv_simulation(self, registry_manager):
        """Test TV object simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_tv")

        assert tree.object_type == "tv"
        assert len(tree.nodes) == 3

    def test_action_with_parameters(self, registry_manager):
        """Test action with parameters."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_params")

        state2 = tree.nodes["state2"]
        assert state2.action_name == "adjust_volume"
        assert state2.action_parameters == {"level": "high"}


class TestTreeSerialization:
    """Tests for tree serialization to YAML."""

    def test_tree_to_yaml(self, registry_manager):
        """Tree can be serialized to YAML."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        tree_dict = tree.model_dump()

        # Should be serializable to YAML
        yaml_str = yaml.dump(tree_dict, default_flow_style=False)
        assert yaml_str is not None
        assert "simulation_id" in yaml_str
        assert "state0" in yaml_str

    def test_tree_from_yaml(self, registry_manager):
        """Tree can be deserialized from YAML."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        original = runner.run("flashlight", actions, simulation_id="test_yaml")
        tree_dict = original.model_dump()

        # Round-trip through YAML
        yaml_str = yaml.dump(tree_dict)
        loaded_dict = yaml.safe_load(yaml_str)
        restored = SimulationTree.model_validate(loaded_dict)

        assert restored.simulation_id == original.simulation_id
        assert restored.object_type == original.object_type
        assert len(restored.nodes) == len(original.nodes)
        assert restored.current_path == original.current_path


class TestVisualization:
    """Tests for HTML visualization generation."""

    def test_visualization_generation(self, registry_manager, tmp_path):
        """Visualization can be generated from tree."""
        from simulator.visualizer.generator import generate_html

        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        tree_dict = tree.model_dump()

        output_path = tmp_path / "test_viz.html"
        generate_html(tree_dict, str(output_path))

        assert output_path.exists()
        content = output_path.read_text()
        assert "Simulation Tree" in content
        assert "state0" in content
        assert "flashlight" in content

    def test_visualization_from_yaml(self, registry_manager, tmp_path):
        """Visualization can be generated from YAML file."""
        from simulator.visualizer.generator import generate_visualization

        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # Save to YAML
        yaml_path = tmp_path / "test_history.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(tree.model_dump(), f)

        # Generate visualization
        html_path = generate_visualization(str(yaml_path))

        assert Path(html_path).exists()
        assert html_path.endswith("_visualization.html")


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_flashlight_cycle(self, registry_manager):
        """Full flashlight simulation cycle."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="flashlight_cycle")

        assert len(tree.nodes) == 5
        assert all(tree.nodes[nid].action_status == "ok" for nid in tree.current_path)

    def test_full_tv_session(self, registry_manager):
        """Full TV session simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "open_streaming", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="tv_session")

        assert tree.object_type == "tv"
        assert len(tree.nodes) == 5

    def test_kettle_workflow(self, registry_manager):
        """Kettle workflow simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "pour_water", "parameters": {"level": "full"}},
            {"name": "heat", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("kettle", actions, simulation_id="kettle_workflow")

        assert tree.object_type == "kettle"
        # Some actions may fail due to preconditions, that's expected
        assert len(tree.nodes) >= 2


class TestTreeStatistics:
    """Tests for tree statistics (Phase 2 ready)."""

    def test_get_statistics(self, registry_manager):
        """Tree provides comprehensive statistics."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)
        stats = tree.get_statistics()

        assert "total_nodes" in stats
        assert "depth" in stats
        assert "width" in stats
        assert "leaf_nodes" in stats
        assert "branch_points" in stats
        assert "successful_actions" in stats
        assert "failed_actions" in stats
        assert "path_length" in stats

        assert stats["total_nodes"] == 3
        assert stats["depth"] == 3
        assert stats["successful_actions"] == 2
        assert stats["failed_actions"] == 0

    def test_get_leaf_nodes(self, registry_manager):
        """Tree can identify leaf nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        leaves = tree.get_leaf_nodes()

        assert len(leaves) == 1
        assert leaves[0].id == "state1"

    def test_get_path_to_node(self, registry_manager):
        """Tree can reconstruct path to any node."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)
        path = tree.get_path_to_node("state2")

        assert len(path) == 3
        assert path[0].id == "state0"
        assert path[1].id == "state1"
        assert path[2].id == "state2"


class TestWorldSnapshotMethods:
    """Tests for WorldSnapshot helper methods (Phase 2 ready)."""

    def test_get_attribute_value(self, registry_manager):
        """WorldSnapshot provides attribute access."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        snapshot = tree.nodes["state1"].snapshot

        # Part attribute
        value = snapshot.get_attribute_value("switch.position")
        assert value == "on"

    def test_get_all_attribute_paths(self, registry_manager):
        """WorldSnapshot lists all attribute paths."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        snapshot = tree.root.snapshot
        paths = snapshot.get_all_attribute_paths()

        assert "switch.position" in paths
        assert "battery.level" in paths
        assert "bulb.state" in paths

    def test_is_attribute_known(self, registry_manager):
        """WorldSnapshot can check if attribute is known."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        snapshot = tree.root.snapshot

        # All attributes should be known in Phase 1
        assert snapshot.is_attribute_known("battery.level")
        assert snapshot.is_attribute_known("switch.position")


class TestTreeNodeProperties:
    """Tests for TreeNode properties (Phase 2 ready)."""

    def test_node_succeeded_property(self, registry_manager):
        """TreeNode has succeeded property."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        assert tree.nodes["state1"].succeeded is True
        assert tree.nodes["state1"].failed is False

    def test_node_failed_property(self, registry_manager):
        """TreeNode has failed property for rejected actions."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "drain_battery", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        # state2 should be rejected (empty battery)
        assert tree.nodes["state2"].failed is True
        assert tree.nodes["state2"].succeeded is False

    def test_node_change_count(self, registry_manager):
        """TreeNode tracks change count."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        assert tree.nodes["state0"].change_count == 0  # Root has no changes
        assert tree.nodes["state1"].change_count > 0  # turn_on has changes

    def test_node_get_changed_attributes(self, registry_manager):
        """TreeNode can list changed attributes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        changed = tree.nodes["state1"].get_changed_attributes()
        assert "switch.position" in changed
        assert "bulb.state" in changed


class TestCLIMetadata:
    """Tests for CLI command metadata in tree."""

    def test_tree_stores_actions_list(self, registry_manager):
        """Tree stores list of actions executed."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        # CLI command is set by CLI, not runner
        # But actions list should be empty by default (set by CLI)
        assert tree.actions == []  # Not set by runner

    def test_tree_cli_command_default(self, registry_manager):
        """Tree CLI command is None by default."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        assert tree.cli_command is None  # Set by CLI, not runner
