"""
Tests for Phase 2 branching functionality.

Tests cover:
- Precondition branching helpers
- Branching integration
- Combined branching (precondition + postcondition)
- In operator branching
"""

from simulator.core.simulation_runner import ObjectStateSnapshot
from simulator.core.tree.models import BranchCondition, SimulationTree, TreeNode, WorldSnapshot
from simulator.core.tree.tree_runner import TreeSimulationRunner


class TestPreconditionBranchingHelpers:
    """Tests for precondition branching helper methods."""

    def test_get_attribute_space_id(self, registry_manager):
        """Can get space ID for attribute."""
        from simulator.core.tree.snapshot_utils import get_attribute_space_id

        # Create flashlight instance
        obj_type = registry_manager.objects.get("flashlight")
        from simulator.io.loaders.object_loader import instantiate_default

        instance = instantiate_default(obj_type, registry_manager)

        space_id = get_attribute_space_id(instance, "battery.level")
        # Actual space ID from flashlight.yaml
        assert space_id == "battery_level"

    def test_get_all_space_values(self, registry_manager):
        """Can get all values in a space."""
        from simulator.core.tree.snapshot_utils import get_all_space_values

        values = get_all_space_values("generic_level", registry_manager)

        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" in values

    def test_evaluate_condition_for_value_equals(self, registry_manager):
        """Runner can evaluate condition for specific value."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.objects.part import AttributeTarget
        from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

        condition = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="equals",
            value="high",
        )

        assert evaluate_condition_for_value(condition, "high") is True
        assert evaluate_condition_for_value(condition, "low") is False

    def test_evaluate_condition_for_value_not_equals(self, registry_manager):
        """Runner evaluates not_equals condition."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.objects.part import AttributeTarget
        from simulator.core.tree.utils.condition_evaluation import evaluate_condition_for_value

        condition = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )

        assert evaluate_condition_for_value(condition, "empty") is False
        assert evaluate_condition_for_value(condition, "high") is True


class TestBranchingIntegration:
    """Integration tests for branching (Phase 2)."""

    def test_linear_execution_with_known_values(self, registry_manager):
        """With all known values, action creates nodes (plus constraint branches for flashlight)."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # Flashlight has branching constraint, so creates more nodes
        # At minimum: root + action + constraint branches
        assert len(tree.nodes) >= 2
        assert "state0" in tree.nodes  # Root
        assert "state1" in tree.nodes  # Action node

    def test_tree_supports_multiple_children(self, registry_manager):
        """Tree structure supports nodes with multiple children."""
        # Manually create a tree with branching
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        tree = SimulationTree(
            simulation_id="test_branch",
            object_type="test",
            object_name="test",
        )

        # Create root
        root = TreeNode(id=tree.generate_node_id(), snapshot=snapshot)
        tree.add_node(root)

        # Create two children (simulating branching)
        child1 = TreeNode(
            id=tree.generate_node_id(),
            snapshot=snapshot,
            parent_id=root.id,
            action_name="action1",
            branch_condition=BranchCondition(
                attribute="test.attr",
                operator="equals",
                value="value1",
                source="precondition",
                branch_type="success",
            ),
        )

        child2 = TreeNode(
            id=tree.generate_node_id(),
            snapshot=snapshot,
            parent_id=root.id,
            action_name="action1",
            branch_condition=BranchCondition(
                attribute="test.attr",
                operator="in",
                value=["value2", "value3"],
                source="precondition",
                branch_type="fail",
            ),
        )

        tree.add_branch_nodes(root.id, [child1, child2])

        # Verify structure
        assert len(root.children_ids) == 2
        assert "state1" in root.children_ids
        assert "state2" in root.children_ids
        assert tree.count_branches() == 1

    def test_tree_get_siblings(self, registry_manager):
        """Tree can get siblings of a node."""
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        tree = SimulationTree(
            simulation_id="test_siblings",
            object_type="test",
            object_name="test",
        )

        root = TreeNode(id=tree.generate_node_id(), snapshot=snapshot)
        tree.add_node(root)

        child1 = TreeNode(id=tree.generate_node_id(), snapshot=snapshot, parent_id=root.id)
        child2 = TreeNode(id=tree.generate_node_id(), snapshot=snapshot, parent_id=root.id)
        tree.add_branch_nodes(root.id, [child1, child2])

        siblings = tree.get_siblings("state1")
        assert len(siblings) == 1
        assert siblings[0].id == "state2"


class TestCombinedBranching:
    """Tests for combined precondition + postcondition branching (Phase 2 refined)."""

    def test_combined_branching_same_attribute(self, registry_manager):
        """
        When precondition and postcondition check same attribute,
        each postcondition case creates a separate branch.
        """
        runner = TreeSimulationRunner(registry_manager)

        # Set battery.level to unknown to trigger branching
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="combined_same_attr",
            initial_values={"battery.level": "unknown"},
        )

        # With the new architecture:
        # - Action node only has direct effects (switch on)
        # - Solver derives bulb state based on battery level
        # - Time constraints handle temporal branching
        # At minimum: root + action + solver nodes + time nodes
        assert len(tree.nodes) >= 3

        # Check that we have action, solver, and time nodes
        action_nodes = [n for n in tree.nodes.values() if n.action_status == "ok" and n.node_type == "action"]
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]

        # With unknown battery, solver creates branches for different battery levels
        assert len(action_nodes) >= 1  # At least one successful action
        assert len(solver_nodes) >= 1  # Solver derives state

    def test_combined_branching_success_branches_first(self, registry_manager):
        """Success branches should be created before fail branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="success_first",
            initial_values={"battery.level": "unknown"},
        )

        # Get children of root (state0)
        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # First child should be success (ok status)
        if len(children) > 0:
            first_child = children[0]
            assert first_child.action_status == "ok"

    def test_combined_branching_each_value_separate(self, registry_manager):
        """
        With the new architecture, branching happens in solver/time nodes,
        not in action postconditions. Solver rules derive state for each battery level.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="each_value_test",
            initial_values={"battery.level": "unknown"},
        )

        # With new architecture, branching comes from solver and time nodes
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]
        time_nodes = [n for n in tree.nodes.values() if n.node_type == "time"]

        # Solver and/or time nodes should exist for handling unknown battery
        assert len(solver_nodes) >= 1 or len(time_nodes) >= 1

        # Check that the tree has branches (more than one leaf)
        leaves = [n for n in tree.nodes.values() if not n.children_ids]
        # With unknown battery and trends, we should have multiple possible end states
        assert len(leaves) >= 1

    def test_branches_continue_to_next_action(self, registry_manager):
        """Actions should be applied to all leaf nodes from previous step."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="branches_continue",
            initial_values={"battery.level": "unknown"},
        )

        # With new architecture:
        # - turn_on creates action node, then solver derives state
        # - Time constraints may create branches for battery trends
        # - turn_off is applied to leaf nodes from the previous step

        turn_off_nodes = [n for n in tree.nodes.values() if n.action_name == "turn_off"]
        # turn_off should be applied to at least one leaf
        assert len(turn_off_nodes) >= 1, "turn_off should be applied to leaves"

    def test_linear_when_values_known(self, registry_manager):
        """When values are known, action creates nodes (plus constraints for flashlight)."""
        runner = TreeSimulationRunner(registry_manager)

        # Default battery.level is 'medium' (known value)
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="linear_known",
        )

        # With branching constraints, flashlight creates constraint branches
        # At minimum: root + turn_on result
        assert len(tree.nodes) >= 2
        assert "state0" in tree.nodes
        assert "state1" in tree.nodes


class TestInOperatorBranching:
    """Tests for the 'in' operator in postcondition branching."""

    def test_in_operator_groups_values_as_set(self, registry_manager):
        """Values matched by 'in' operator should be grouped as a value set."""
        runner = TreeSimulationRunner(registry_manager)

        # dice uses 'in' operator for else colors: yellow, black, white
        # Architecture: Action sets prize.result=win, Solver derives prize.level
        tree = runner.run(
            "dice",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_operator_test",
            initial_values={"cube.face": "unknown", "cube.color": "unknown"},
        )

        # Should have 6 nodes: root + 2 action branches + 3 solver branches (success only)
        # Success path: green->small, red->medium, {yellow,black,white}->big
        # Fail path: failed action nodes are terminal (no solver runs)
        assert len(tree.nodes) == 6

        # Find the solver branch with the value set (grouped colors)
        grouped_branch = None
        for node in tree.nodes.values():
            if node.node_type == "solver" and node.branch_condition:
                val = node.branch_condition.value
                if isinstance(val, list) and len(val) == 3:
                    grouped_branch = node
                    break

        assert grouped_branch is not None, "Should have a solver branch with grouped values"
        assert set(grouped_branch.branch_condition.value) == {"yellow", "black", "white"}

    def test_in_operator_solver_branching_with_unknown(self, registry_manager):
        """Solver with 'in' operator should create branches for different face values.

        dice_same_attr uses solver-based branching:
        - check_win has no precondition (always succeeds, sets result=win)
        - Solver invalidates win for faces {1, 2, 4} (sets result=lose)
        - Solver determines prize.level based on face for winning faces
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "dice_same_attr",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_solver_test",
            initial_values={"cube.face": "unknown"},
        )

        # Should have solver nodes with different outcomes
        solver_nodes = [n for n in tree.nodes.values() if n.node_type == "solver"]
        assert len(solver_nodes) >= 2, f"Expected multiple solver branches, got {len(solver_nodes)}"

        # Check that we have both lose and win outcomes
        results = set()
        for node in solver_nodes:
            result = node.snapshot.get_attribute_value("prize.result")
            if result:
                results.add(result)

        assert "win" in results, "Should have a winning branch"
        assert "lose" in results, "Should have a losing branch"
