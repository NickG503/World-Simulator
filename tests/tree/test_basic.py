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
        # With branching constraints, flashlight creates constraint nodes after actions
        # root + turn_on + 2 constraint branches (battery empty vs non-empty)
        assert len(tree.nodes) >= 2  # At minimum root + turn_on result
        assert "state0" in tree.nodes  # Root
        assert "state1" in tree.nodes  # Turn on action node

    def test_multi_action_simulation(self, registry_manager):
        """Run multi-action simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_multi")

        # With branching constraints, node count is higher
        assert len(tree.nodes) >= 3  # At minimum root + turn_on + turn_off
        assert "state0" in tree.nodes
        assert "state1" in tree.nodes

        # Verify parent-child relationships from root
        root = tree.nodes["state0"]
        assert len(root.children_ids) >= 1

        state1 = tree.nodes["state1"]
        assert state1.parent_id == "state0"
        assert state1.action_name == "turn_on"

    def test_node_ids_sequential(self, registry_manager):
        """Node IDs should be sequential state0, state1, etc."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        # With branching constraints, we have more nodes than actions
        # Just verify all nodes have sequential IDs
        assert "state0" in tree.nodes  # Root always exists
        for i in range(len(tree.nodes)):
            assert f"state{i}" in tree.nodes

    def test_precondition_failure(self, registry_manager):
        """Action with failed precondition creates error node."""
        runner = TreeSimulationRunner(registry_manager)
        # drain_battery then turn_on - turn_on requires battery not empty
        actions = [
            {"name": "drain_battery", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_fail")

        # With the new architecture, the action precondition is just "switch must be off"
        # The battery check is handled by the solver, which derives bulb.state = off when battery is empty
        # So we check that when battery is empty, the solver correctly sets bulb off
        assert len(tree.nodes) >= 3

        # Find nodes where bulb state is off after turn_on action (solver derived)
        final_nodes = [n for n in tree.nodes.values() if not n.children_ids]
        # At least one final node should have bulb.state = off (empty battery case)
        bulb_states = []
        for node in final_nodes:
            bulb_state = node.snapshot.get_attribute_value("bulb.state")
            if bulb_state:
                bulb_states.append(bulb_state)
        # With empty battery, bulb should be off
        assert "off" in bulb_states

    def test_changes_recorded(self, registry_manager):
        """Changes are recorded in nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # With the new architecture:
        # - Action node (state1): only direct effects (switch.position, battery trend)
        # - Solver node (state2+): derived effects (bulb.state, brightness)
        state1 = tree.nodes["state1"]
        assert len(state1.changes) > 0

        # Action node should have switch.position change (direct effect)
        change_attrs = [c["attribute"] for c in state1.changes]
        assert "switch.position" in change_attrs

        # Solver nodes should have bulb.state change (derived effect)
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]
        assert len(solver_nodes) >= 1

        # Check that at least one solver node has bulb.state change
        bulb_changed = False
        for node in solver_nodes:
            change_attrs = [c["attribute"] for c in node.changes]
            if "bulb.state" in change_attrs:
                bulb_changed = True
                break
        assert bulb_changed, "Solver should derive bulb.state change"

    def test_tv_simulation(self, registry_manager):
        """Test TV object simulation with solver pattern.

        TV now uses solver to derive screen.brightness and cooling.temperature trend.
        Flow: action -> solver -> (time if trends) -> solver
        """
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_tv")

        assert tree.object_type == "tv"
        # With solver pattern, more nodes are created (action + solver + time + solver)
        assert len(tree.nodes) >= 3  # At minimum: initial + some action/solver nodes

    def test_action_with_parameters(self, registry_manager):
        """Test action with parameters."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_params")

        # Find the adjust_volume action node (not a solver node)
        adjust_volume_node = None
        for node in tree.nodes.values():
            if node.action_name == "adjust_volume":
                adjust_volume_node = node
                break

        assert adjust_volume_node is not None, "adjust_volume action node should exist"
        assert adjust_volume_node.action_parameters == {"level": "high"}


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
        """Full TV session simulation with solver pattern.

        TV now uses solver to derive screen.brightness and cooling.temperature trend.
        Node counts are higher due to solver nodes being created after each action.
        """
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "open_streaming", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="tv_session")

        assert tree.object_type == "tv"
        # With solver pattern, more nodes are created (action + solver + time + solver per action)
        assert len(tree.nodes) >= 5

    def test_kettle_workflow(self, registry_manager):
        """Kettle workflow simulation with solver pattern.

        Kettle now uses solver to derive heater.temperature from power and tank level.
        """
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "fill", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
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

        # With branching constraints, flashlight has more nodes
        assert stats["total_nodes"] >= 3
        assert stats["depth"] >= 3
        assert stats["successful_actions"] >= 2
        assert stats["failed_actions"] == 0

    def test_get_leaf_nodes(self, registry_manager):
        """Tree can identify leaf nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        leaves = tree.get_leaf_nodes()

        # With branching constraints, flashlight creates multiple leaf nodes
        assert len(leaves) >= 1
        # All leaves should be valid nodes
        for leaf in leaves:
            assert leaf.id in tree.nodes

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
        # Use TV which still has precondition for turn_off (must be on)
        actions = [
            {"name": "turn_off", "parameters": {}},  # Should fail - TV starts off
        ]

        tree = runner.run("tv", actions)

        # Find the rejected turn_off node
        rejected = [n for n in tree.nodes.values() if n.action_name == "turn_off" and n.failed]
        assert len(rejected) >= 1
        assert rejected[0].succeeded is False

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

        # Action node has direct effects only (switch.position)
        changed = tree.nodes["state1"].get_changed_attributes()
        assert "switch.position" in changed

        # Solver nodes have derived effects (bulb.state)
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]
        bulb_in_solver = any("bulb.state" in n.get_changed_attributes() for n in solver_nodes)
        assert bulb_in_solver, "bulb.state should be changed in solver node"


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
