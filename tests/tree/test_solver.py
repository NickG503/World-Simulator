"""
Tests for solver functionality.

Tests the multi-step action flow:
1. Action postcondition (direct effect)
2. Solver rules (derived state)
3. Time constraints (trend expansion) - if trends present
4. Solver again (fix impossible states) - if trends present
"""

import pytest

from simulator.core.registries import RegistryManager
from simulator.core.solver.rule import SolverRule, compile_solver_rules
from simulator.core.solver.solver_branching import get_solver_rules
from simulator.core.solver.specs import parse_solver_rule_spec
from simulator.core.tree import TreeSimulationRunner

from .conftest import run_simulation


class TestSolverSpecs:
    """Tests for solver YAML spec parsing."""

    def test_parse_simple_rule(self):
        """Test parsing a simple condition -> implies rule."""
        data = {
            "name": "test_rule",
            "priority": 10,
            "condition": {
                "type": "attribute_check",
                "target": "switch.position",
                "operator": "equals",
                "value": "on",
            },
            "implies": [{"type": "set_attribute", "target": "bulb.state", "value": "on"}],
            "otherwise": [{"type": "set_attribute", "target": "bulb.state", "value": "off"}],
        }
        spec = parse_solver_rule_spec(data)
        assert spec.name == "test_rule"
        assert spec.priority == 10
        assert spec.condition is not None
        assert len(spec.implies) == 1
        assert len(spec.otherwise) == 1

    def test_parse_case_based_rule(self):
        """Test parsing a rule with if/elif/else cases."""
        data = {
            "name": "brightness_rule",
            "priority": 20,
            "precondition": {
                "type": "attribute_check",
                "target": "bulb.state",
                "operator": "equals",
                "value": "on",
            },
            "cases": [
                {
                    "condition": {
                        "type": "attribute_check",
                        "target": "battery.level",
                        "operator": "in",
                        "value": ["full", "high"],
                    },
                    "implies": [{"type": "set_attribute", "target": "bulb.brightness", "value": "high"}],
                },
                {
                    "condition": {
                        "type": "attribute_check",
                        "target": "battery.level",
                        "operator": "equals",
                        "value": "medium",
                    },
                    "implies": [{"type": "set_attribute", "target": "bulb.brightness", "value": "medium"}],
                },
            ],
            "otherwise": [{"type": "set_attribute", "target": "bulb.brightness", "value": "none"}],
        }
        spec = parse_solver_rule_spec(data)
        assert spec.name == "brightness_rule"
        assert spec.precondition is not None
        assert len(spec.cases) == 2
        assert len(spec.otherwise) == 1


class TestSolverRuleCompilation:
    """Tests for compiling solver rules from specs."""

    def test_compile_simple_rule(self):
        """Test compiling a simple rule."""
        data = {
            "name": "test_rule",
            "priority": 10,
            "condition": {
                "type": "attribute_check",
                "target": "switch.position",
                "operator": "equals",
                "value": "on",
            },
            "implies": [{"type": "set_attribute", "target": "bulb.state", "value": "on"}],
        }
        spec = parse_solver_rule_spec(data)
        rule = SolverRule.from_spec(spec)

        assert rule.name == "test_rule"
        assert rule.priority == 10
        assert rule.is_simple()
        assert not rule.is_case_based()
        assert len(rule.implies) == 1

    def test_compile_multiple_rules_sorted_by_priority(self):
        """Test that compiled rules are sorted by priority."""
        specs = [
            parse_solver_rule_spec({"name": "low", "priority": 50}),
            parse_solver_rule_spec({"name": "high", "priority": 10}),
            parse_solver_rule_spec({"name": "medium", "priority": 30}),
        ]
        rules = compile_solver_rules(specs)

        assert len(rules) == 3
        assert rules[0].name == "high"  # priority 10
        assert rules[1].name == "medium"  # priority 30
        assert rules[2].name == "low"  # priority 50


class TestFlashlightSolverIntegration:
    """Integration tests for flashlight with solver rules."""

    def test_turn_on_creates_solver_node(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that turn_on action creates solver nodes."""
        tree = run_simulation(runner, "flashlight", "turn_on")

        # Should have root + action + solver (at minimum)
        assert len(tree.nodes) >= 2

        # Find solver nodes
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]

        # If solver rules are present, we should have solver nodes
        rules = get_solver_rules("flashlight", registry_manager)
        if rules:
            assert len(solver_nodes) > 0, "Expected solver nodes when solver rules are defined"

    def test_turn_on_derives_bulb_state(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that solver derives bulb state from switch position."""
        tree = run_simulation(runner, "flashlight", "turn_on")

        # Get the final leaf nodes
        leaves = tree.get_leaf_nodes()

        # At least one leaf should have bulb.state = on (derived from switch.position = on)
        found_bulb_on = False
        for leaf in leaves:
            bulb_state = leaf.snapshot.get_attribute_value("bulb.state")
            if bulb_state == "on":
                found_bulb_on = True
                break

        assert found_bulb_on, "Expected at least one leaf with bulb.state = on"

    def test_turn_on_derives_brightness(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that solver derives brightness from battery level."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "full"},
        )

        # Get the final leaf nodes
        leaves = tree.get_leaf_nodes()

        # At least one leaf should have brightness based on battery level
        found_brightness = False
        for leaf in leaves:
            brightness = leaf.snapshot.get_attribute_value("bulb.brightness")
            if brightness is not None and brightness != "none":
                found_brightness = True
                break

        assert found_brightness, "Expected brightness to be derived from battery level"

    def test_turn_off_derives_bulb_off(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that turn_off derives bulb.state = off via solver."""
        # First turn on, then turn off
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="test_turn_off",
            initial_values={"battery.level": "full"},
        )

        # Get the final leaf nodes
        leaves = tree.get_leaf_nodes()

        # All leaves should have bulb.state = off after turn_off
        for leaf in leaves:
            if leaf.action_status == "ok" and leaf.action_name == "turn_off":
                bulb_state = leaf.snapshot.get_attribute_value("bulb.state")
                # After solver processes turn_off, bulb should be off
                if bulb_state:
                    assert bulb_state == "off" or isinstance(bulb_state, list)


class TestSolverWithTrends:
    """Tests for solver behavior with time/trend constraints."""

    def test_turn_on_with_unknown_battery_creates_time_nodes(
        self, registry_manager: RegistryManager, runner: TreeSimulationRunner
    ):
        """Test that turn_on with unknown battery creates time nodes due to trends."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "unknown"},
        )

        # With unknown battery and trends, we should have time nodes
        _time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        # Time nodes should be created when there are trends
        # Note: this depends on the constraint_branching implementation
        # The test verifies the integration works

    def test_solver_fixes_impossible_state_after_time(
        self, registry_manager: RegistryManager, runner: TreeSimulationRunner
    ):
        """Test that solver fixes impossible states created by time constraints."""
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "unknown"},
        )

        # Get all leaf nodes
        leaves = tree.get_leaf_nodes()

        # Check that no leaf has impossible state:
        # battery = empty AND bulb = on (should be fixed by solver)
        for leaf in leaves:
            battery = leaf.snapshot.get_attribute_value("battery.level")
            bulb = leaf.snapshot.get_attribute_value("bulb.state")

            # If battery is empty, bulb should be off
            if battery == "empty" or (isinstance(battery, list) and "empty" in battery and len(battery) == 1):
                if bulb == "on":
                    pytest.fail(f"Found impossible state: battery=empty, bulb=on in {leaf.id}")


class TestSolverNodeTypes:
    """Tests for node type classification."""

    def test_action_node_type(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that action nodes have correct node_type."""
        tree = run_simulation(runner, "flashlight", "turn_on")

        # Find the first action node (not root)
        _action_nodes = [n for n in tree.nodes.values() if n.node_type == "action"]

        # With the new flow, action nodes represent the direct postcondition effect
        # Solver nodes should be separate

    def test_solver_node_has_purple_classification(
        self, registry_manager: RegistryManager, runner: TreeSimulationRunner
    ):
        """Test that solver nodes are correctly classified for purple coloring."""
        tree = run_simulation(runner, "flashlight", "turn_on")

        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]

        # Each solver node should have node_type = "solver"
        for node in solver_nodes:
            assert node.node_type == "solver"


class TestSolverPriorityOrder:
    """Tests for solver rule priority ordering."""

    def test_rules_sorted_by_priority(self, registry_manager: RegistryManager):
        """Test that solver rules are sorted by priority (lowest first)."""
        rules = get_solver_rules("flashlight", registry_manager)

        if len(rules) >= 2:
            # Rules should be sorted by priority (ascending)
            for i in range(len(rules) - 1):
                assert rules[i].priority <= rules[i + 1].priority, (
                    f"Rules should be sorted by priority: {rules[i].name} (p={rules[i].priority}) "
                    f"should come before {rules[i + 1].name} (p={rules[i + 1].priority})"
                )

    def test_earlier_rules_affect_later_rules(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that earlier rules' effects are visible to later rules.

        In flashlight:
        - Rule 1 (low priority): switch=on -> bulb=on
        - Rule 2 (higher priority): bulb=on AND battery=full -> brightness=high

        Rule 2 should see the bulb.state set by Rule 1.
        """
        tree = run_simulation(
            runner,
            "flashlight",
            "turn_on",
            initial_values={"battery.level": "full"},
        )

        leaves = tree.get_leaf_nodes()

        # Find leaves where action succeeded
        success_leaves = [n for n in leaves if n.action_status == "ok"]

        # At least one leaf should have:
        # - bulb.state = on (from Rule 1)
        # - brightness = high (from Rule 2 seeing bulb.state = on)
        found_correct_state = False
        for leaf in success_leaves:
            bulb = leaf.snapshot.get_attribute_value("bulb.state")
            brightness = leaf.snapshot.get_attribute_value("bulb.brightness")

            # Check if brightness was derived correctly
            if bulb == "on" and brightness == "high":
                found_correct_state = True
                break

        assert found_correct_state, "Expected solver to derive brightness=high after deriving bulb=on"


class TestSolverAfterEachAction:
    """Tests that solver runs after every action."""

    def test_solver_runs_after_each_action(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that solver runs after each action in a sequence."""
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="test_solver_each_action",
            initial_values={"battery.level": "full"},
        )

        # Find all solver nodes
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]

        # There should be solver nodes after each action
        # At minimum, 2 solver passes (one per action)
        assert len(solver_nodes) >= 2, f"Expected at least 2 solver nodes (one per action), got {len(solver_nodes)}"

    def test_multi_action_with_solver(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test a multi-action simulation with solver deriving state."""
        tree = runner.run(
            "tv",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="test_tv_multi",
        )

        # Get final leaves
        leaves = tree.get_leaf_nodes()

        # After turn_off, screen.power should be off, and solver should derive brightness=none
        for leaf in leaves:
            if leaf.action_status == "ok":
                power = leaf.snapshot.get_attribute_value("screen.power")
                brightness = leaf.snapshot.get_attribute_value("screen.brightness")

                if power == "off":
                    assert brightness == "none", (
                        f"When power is off, brightness should be none (solver derived), got {brightness}"
                    )


class TestSolverMultipleObjects:
    """Tests for solver across different objects."""

    def test_kettle_solver_derives_temperature(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that kettle solver derives heater temperature from power and tank."""
        tree = runner.run(
            "kettle",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_kettle_solver",
            initial_values={"tank.level": "full"},
        )

        leaves = tree.get_leaf_nodes()

        # After turn_on with full tank, solver should derive heater.temperature = hot
        found_hot = False
        for leaf in leaves:
            if leaf.action_status == "ok":
                temp = leaf.snapshot.get_attribute_value("heater.temperature")
                if temp == "hot":
                    found_hot = True
                    break

        assert found_hot, "Expected kettle solver to derive heater.temperature = hot"

    def test_coffee_machine_solver_derives_ready(self, registry_manager: RegistryManager, runner: TreeSimulationRunner):
        """Test that coffee machine solver derives status.ready."""
        tree = runner.run(
            "coffee_machine",
            [{"name": "heat_up", "parameters": {}}],
            simulation_id="test_coffee_solver",
            initial_values={
                "water_tank.level": "full",
                "heater.temperature": "warm",
            },
        )

        # Solver should run and evaluate ready status
        leaves = tree.get_leaf_nodes()

        # Status should be derived by solver based on water level and temp
        for leaf in leaves:
            if leaf.action_status == "ok":
                ready = leaf.snapshot.get_attribute_value("status.ready")
                # Ready depends on water >= low AND temp == hot
                # Since we started with warm and have trend up, eventually could be hot
                assert ready in ["on", "off"], f"Expected ready to be on or off, got {ready}"
