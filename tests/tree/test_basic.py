"""
Tests for basic tree simulation functionality.

Tests cover:
- TreeSimulationRunner basic execution
- End-to-end workflows
- Statistics
- WorldSnapshot methods
- TreeNode properties
- CLI metadata
"""

from simulator.core.tree.tree_runner import TreeSimulationRunner


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

        # With value sets from trends, we get branching:
        # turn_on creates value set {empty, low, medium}
        # turn_off now requires switch.position == "on" precondition
        # This results in branching with some success and some fail paths
        assert len(tree.nodes) >= 5
        # At least some successful nodes exist
        successful_nodes = [n for n in tree.nodes.values() if n.action_status == "ok"]
        assert len(successful_nodes) >= 3  # root + at least some successes

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
    """Tests for tree statistics."""

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
    """Tests for WorldSnapshot helper methods."""

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
    """Tests for TreeNode properties."""

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
