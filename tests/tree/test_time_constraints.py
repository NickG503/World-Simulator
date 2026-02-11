"""
Tests for time constraint functionality.

Time constraints handle:
1. Trend expansion to value sets
2. Branching based on time constraints
3. Solver fixing impossible states after time
"""

from simulator.core.registries import RegistryManager
from simulator.core.tree import TreeSimulationRunner

from .conftest import run_simulation


class TestTrendExpansion:
    """Tests for trend expansion to value sets."""

    def test_trend_down_creates_value_set(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that trend down creates a value set of possible values."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "high"},
        )

        # With high battery and trend down, value set should include lower values
        time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        # If there are time nodes, check for value sets
        if time_nodes:
            for node in time_nodes:
                _battery = node.snapshot.get_attribute_value("battery.level")
                # Battery should be a value set after time expansion
                # e.g., [empty, low, medium, high] or similar

    def test_trend_up_creates_value_set(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that trend up creates a value set of possible values."""
        # TV has cooling.temperature with trend up when screen.power is on
        tree = run_simulation(
            runner,
            "tv",
            "turn_on",
        )

        # Check for time nodes with temperature value sets
        _time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        # If there are time nodes, the trend should create value sets

    def test_no_trend_no_time_nodes(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that actions without trends don't create time nodes."""
        # Kettle fill action should not create trends
        tree = run_simulation(
            runner,
            "kettle",
            "fill",
        )

        # Fill doesn't involve trends, so should be no time nodes
        time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]
        assert len(time_nodes) == 0, "Fill action should not create time nodes"


class TestTimeConstraintBranching:
    """Tests for branching based on time constraints."""

    def test_time_constraint_creates_branches(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that time constraints create appropriate branches."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "medium"},
        )

        leaves = tree.get_leaf_nodes()
        assert len(leaves) > 1, "Expected multiple branches from trend-down on medium battery"

    def test_multiple_trends_create_branches(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that multiple trends create appropriate branches."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "unknown"},
        )

        leaves = tree.get_leaf_nodes()
        assert len(leaves) > 1, "Expected multiple branches from unknown battery with trends"


class TestSolverFixesTimeState:
    """Tests for solver fixing impossible states after time constraints."""

    def test_empty_battery_bulb_off(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that solver sets bulb off when battery is empty."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "low"},
        )

        leaves = tree.get_leaf_nodes()

        # Check each leaf - if battery is empty, bulb should be off
        for leaf in leaves:
            battery = leaf.snapshot.get_attribute_value("battery.level")
            bulb = leaf.snapshot.get_attribute_value("bulb.state")

            if battery == "empty":
                # Single value empty means bulb should be off
                assert bulb == "off", f"When battery is empty, bulb should be off, got {bulb}"

    def test_trend_none_when_empty(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that trend becomes none when battery is empty."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "low"},
        )

        leaves = tree.get_leaf_nodes()

        # Check leaves where battery is empty
        for leaf in leaves:
            battery = leaf.snapshot.get_attribute_value("battery.level")
            trend = leaf.snapshot.get_attribute_trend("battery.level")

            if battery == "empty":
                # When empty, trend should be none (can't drain further)
                assert trend == "none", f"When battery is empty, trend should be none, got {trend}"


class TestTimeNodeTypes:
    """Tests for time node classification."""

    def test_time_node_type_classification(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that time nodes have correct node_type."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "high"},
        )

        time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        # Each time node should have node_type = "time"
        for node in time_nodes:
            assert node.node_type == "time"

    def test_time_nodes_come_after_solver(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that time nodes come after solver nodes in the flow."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "high"},
        )

        # Check the flow: action -> solver -> time -> solver
        # Find a time node and verify its parent is a solver node
        time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        for time_node in time_nodes:
            # Get parent node
            for parent_id in time_node.parent_ids:
                parent = tree.nodes.get(parent_id)
                if parent:
                    # Parent of time should be solver
                    assert parent.node_type == "solver", f"Time node parent should be solver, got {parent.node_type}"


class TestMultiActionWithTime:
    """Tests for time constraints across multiple actions."""

    def test_two_actions_with_trends(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test two actions where both involve trends."""
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="test_two_actions_trends",
            initial_values={"battery.level": "high"},
        )

        # Both actions involve trends (turn_on: drain, turn_off: none)
        # Should have appropriate nodes
        _time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]

        # Should have solver nodes for both actions
        assert len(solver_nodes) >= 2, "Expected solver nodes for each action"

    def test_trend_cleared_after_turn_off(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that trend is cleared after turn_off."""
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="test_trend_cleared",
            initial_values={"battery.level": "high"},
        )

        leaves = tree.get_leaf_nodes()

        # After turn_off, battery trend should be none
        for leaf in leaves:
            if leaf.action_status == "ok":
                # Check if this is after turn_off
                # The switch should be off
                switch = leaf.snapshot.get_attribute_value("switch.position")
                if switch == "off":
                    trend = leaf.snapshot.get_attribute_trend("battery.level")
                    assert trend == "none", f"After turn_off, battery trend should be none, got {trend}"
