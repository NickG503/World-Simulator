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
        """With all known values, execution is still linear."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # Should be linear - 2 nodes (root + action result)
        assert len(tree.nodes) == 2
        assert tree.current_path == ["state0", "state1"]

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

        # With flat if-elif structure ({full,high}/medium/low), should have 5 nodes:
        # - state0: root
        # - state1-3: success branches ({full,high}, medium, low)
        # - state4: fail (precondition fail with empty)
        assert len(tree.nodes) == 5

        # Check that we have success branches first, then fail branch
        success_nodes = [n for n in tree.nodes.values() if n.action_status == "ok" and n.action_name]
        fail_nodes = [n for n in tree.nodes.values() if n.action_status == "rejected"]

        assert len(success_nodes) == 3  # Three postcondition branches ({full,high}, medium, low)
        assert len(fail_nodes) == 1  # One fail branch

        # Verify fail node has empty as its value
        fail_node = fail_nodes[0]
        assert fail_node.branch_condition is not None
        assert fail_node.branch_condition.value == "empty"
        assert fail_node.branch_condition.branch_type == "fail"

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
        With flat if-elif structure, each condition gets its own branch
        with correct effects applied. {full, high} are combined via 'in' operator.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="each_value_test",
            initial_values={"battery.level": "unknown"},
        )

        # Collect all postcondition branches
        postcond_branches = [
            n for n in tree.nodes.values() if n.branch_condition and n.branch_condition.source == "postcondition"
        ]

        # Should have 3 branches: {full,high}, medium, low
        assert len(postcond_branches) == 3

        # Check that we have the expected branch values
        # One branch should have a list value (from 'in' operator)
        list_branches = [n for n in postcond_branches if isinstance(n.branch_condition.value, list)]
        assert len(list_branches) == 1
        assert set(list_branches[0].branch_condition.value) == {"full", "high"}

    def test_branches_continue_to_next_action(self, registry_manager):
        """All branches (including fail) should continue to subsequent actions."""
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

        # After turn_on with unknown battery:
        # - 3 success branches ({full,high}, medium, low)
        # - 1 fail branch (empty)
        # After turn_off applied to all 4:
        # - Should have 4 turn_off nodes

        turn_off_nodes = [n for n in tree.nodes.values() if n.action_name == "turn_off"]
        assert len(turn_off_nodes) == 4, "turn_off should be applied to all 4 branches"

    def test_linear_when_values_known(self, registry_manager):
        """When values are known, no branching occurs."""
        runner = TreeSimulationRunner(registry_manager)

        # Default battery.level is 'medium' (known value)
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="linear_known",
        )

        # Should be linear: root + turn_on result = 2 nodes
        assert len(tree.nodes) == 2
        assert len(tree.current_path) == 2


class TestInOperatorBranching:
    """Tests for the 'in' operator in postcondition branching."""

    def test_in_operator_groups_values_as_set(self, registry_manager):
        """Values matched by 'in' operator should be grouped as a value set."""
        runner = TreeSimulationRunner(registry_manager)

        # dice uses 'in' operator for else colors: yellow, black, white
        tree = runner.run(
            "dice",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_operator_test",
            initial_values={"cube.face": "unknown", "cube.color": "unknown"},
        )

        # Should have 5 nodes: root + 4 branches (green, red, {yellow,black,white}, fail)
        assert len(tree.nodes) == 5

        # Find the branch with the value set (grouped colors)
        grouped_branch = None
        for node in tree.nodes.values():
            if node.branch_condition:
                val = node.branch_condition.value
                if isinstance(val, list) and len(val) == 3:
                    grouped_branch = node
                    break

        assert grouped_branch is not None, "Should have a branch with grouped values"
        assert set(grouped_branch.branch_condition.value) == {"yellow", "black", "white"}

    def test_in_operator_precondition_with_unknown(self, registry_manager):
        """Precondition with 'in' operator should create fail branch for excluded values."""
        runner = TreeSimulationRunner(registry_manager)

        # dice_same_attr: precondition is face IN {3, 5, 6}
        tree = runner.run(
            "dice_same_attr",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_precond_test",
            initial_values={"cube.face": "unknown"},
        )

        # Should have fail branch with face={1, 2, 4}
        fail_nodes = [n for n in tree.nodes.values() if n.action_status == "rejected"]
        assert len(fail_nodes) == 1

        fail_face = fail_nodes[0].snapshot.get_attribute_value("cube.face")
        assert set(fail_face) == {"1", "2", "4"}, f"Expected fail with {{1,2,4}}, got {fail_face}"
