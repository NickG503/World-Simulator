"""
Edge case tests for recursive De Morgan implementation.

Tests cover:
- Edge cases in De Morgan handling
- Nested postcondition limitations
"""

import pytest

from simulator.core.tree.tree_runner import TreeSimulationRunner


class TestRecursiveDeMorganEdgeCases:
    """Edge case tests for recursive De Morgan implementation."""

    def test_no_or_in_any_branch_condition(self, registry_manager):
        """Verify OR never appears in branch conditions - OR means split."""
        runner = TreeSimulationRunner(registry_manager)

        # Test nested compound
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_no_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        def has_or_recursive(bc):
            if bc is None:
                return False
            if bc.compound_type == "or":
                return True
            if bc.sub_conditions:
                return any(has_or_recursive(sub) for sub in bc.sub_conditions)
            return False

        for nid, node in tree.nodes.items():
            if node.branch_condition:
                assert not has_or_recursive(node.branch_condition), (
                    f"Node {nid} has OR in branch condition - OR should split into branches"
                )

    def test_and_with_three_unknowns_creates_three_fail(self, registry_manager):
        """AND with 3 unknowns should create 3 fail branches (De Morgan OR)."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_and_3fail",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # 3 unknowns in AND -> 3 fail branches (one per failing attribute)
        assert len(fail_branches) == 3, f"Expected 3 fail branches, got {len(fail_branches)}"

    def test_or_with_three_unknowns_creates_one_compound_fail(self, registry_manager):
        """OR with 3 unknowns should create 1 fail branch with AND of 3 complements."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_or_1fail",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # 3 unknowns in OR -> 1 fail branch (all must fail)
        assert len(fail_branches) == 1, f"Expected 1 fail branch, got {len(fail_branches)}"

        # The branch should have compound AND with 3 sub-conditions
        bc = fail_branches[0].branch_condition
        assert bc.compound_type == "and"
        assert len(bc.sub_conditions) == 3

    def test_known_value_reduces_fail_branches(self, registry_manager):
        """Known values that satisfy should reduce fail branch count."""
        runner = TreeSimulationRunner(registry_manager)

        # With reel3 known as seven (satisfies OR), no fail branches needed
        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_known_reduces",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "seven",  # Known, satisfies
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # With one satisfying known value, OR always succeeds - no fail branches
        assert len(fail_branches) == 0, f"Expected 0 fail branches, got {len(fail_branches)}"

    def test_nested_demorgan_creates_correct_branch_count(self, registry_manager):
        """Nested (A AND B) OR C should create 2 success + 1 fail.

        For (A AND B) OR C:
        - Success 1: Inner AND satisfied (both A and B must be satisfied together)
        - Success 2: C satisfied
        - Fail 1: De Morgan of OR (all disjuncts fail)
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_branch_count",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # (A AND B) OR C with all unknown:
        # Success: 2 (1 for inner AND satisfied, 1 for C satisfied)
        # Fail: 1 (De Morgan: all disjuncts fail)
        assert len(success) == 2, f"Expected 2 success, got {len(success)}"
        assert len(fail) == 1, f"Expected 1 fail, got {len(fail)}"

    def test_each_fail_branch_has_unique_constraint(self, registry_manager):
        """Each fail branch should constrain different attributes."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_unique_constraints",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Collect which attributes are constrained (not seven) in each branch
        constrained_attrs = []
        for fb in fail_branches:
            attrs = set()
            for reel in ["reel1", "reel2"]:
                val = fb.snapshot.get_attribute_value(f"{reel}.symbol")
                if isinstance(val, list) and "seven" not in val:
                    attrs.add(reel)
            constrained_attrs.append(frozenset(attrs))

        # Each branch should have a different constraint pattern
        assert len(set(constrained_attrs)) == len(fail_branches), (
            "Each fail branch should have unique constraint pattern"
        )

    @pytest.mark.skip(reason="Compound postcondition branching not yet implemented")
    def test_postcondition_and_creates_multiple_else_branches(self, registry_manager):
        """AND in postcondition should create multiple ELSE branches.

        NOTE: This test documents expected behavior for future implementation.
        Currently, compound conditions in postconditions are not branched on.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_postcond_else",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        else_branches = [
            tree.nodes[cid]
            for cid in root.children_ids
            if tree.nodes[cid].branch_condition and tree.nodes[cid].branch_condition.branch_type == "else"
        ]

        # AND with 2 unknowns in postcondition -> 2 else branches
        assert len(else_branches) == 2, f"Expected 2 else branches, got {len(else_branches)}"

    def test_deeply_nested_all_configs_valid(self, registry_manager):
        """All branch configurations should have valid world states."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_valid_configs",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        valid_symbols = ["cherry", "lemon", "bar", "bell", "seven"]

        for nid, node in tree.nodes.items():
            for reel in ["reel1", "reel2", "reel3"]:
                val = node.snapshot.get_attribute_value(f"{reel}.symbol")
                if isinstance(val, list):
                    for v in val:
                        assert v in valid_symbols, f"Invalid value {v} in {nid}"
                elif val != "unknown":
                    assert val in valid_symbols, f"Invalid value {val} in {nid}"


class TestNestedPostconditionLimitations:
    """Test documenting known limitations of nested postconditions.

    NOTE: These tests document expected behavior that is not yet fully implemented.
    Compound postcondition branching and nested else branching are future features.
    """

    @pytest.mark.skip(reason="Nested postcondition branching not yet implemented")
    def test_nested_if_in_else_branches_at_first_level_only(self, registry_manager):
        """
        Currently, nested conditionals inside else branches
        create branches at the first level only.
        This is a known limitation.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_status", "parameters": {}}],
            simulation_id="test_nested_limit",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        # Current behavior: 3 nodes (initial + 2 branches for first condition)
        # NOT 4 nodes (which would be ideal with recursive branching)
        assert len(tree.nodes) == 3

        # The else branch evaluates nested conditional but doesn't branch
        root = tree.nodes["state0"]
        assert len(root.children_ids) == 2

        # One is IF (water >= medium), one is ELSE
        children = [tree.nodes[cid] for cid in root.children_ids]
        if_branch = [c for c in children if c.branch_condition.branch_type == "if"][0]
        else_branch = [c for c in children if c.branch_condition.branch_type == "else"][0]

        # IF branch: water constrained to >= medium
        water_if = if_branch.snapshot.get_attribute_value("water_tank.level")
        assert isinstance(water_if, list)
        assert "medium" in water_if and "high" in water_if and "full" in water_if

        # ELSE branch: water constrained to < medium
        # But temp is NOT branched on (nested limitation)
        water_else = else_branch.snapshot.get_attribute_value("water_tank.level")
        assert isinstance(water_else, list)
        assert "empty" in water_else and "low" in water_else

        # Temperature remains unknown (not branched)
        temp_else = else_branch.snapshot.get_attribute_value("heater.temperature")
        assert temp_else == "unknown"

    @pytest.mark.skip(reason="Compound postcondition branching not yet implemented")
    def test_compound_at_top_level_branches_correctly(self, registry_manager):
        """
        Compound conditions at the top level of postcondition
        DO branch correctly with De Morgan.

        NOTE: This test documents expected behavior for future implementation.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_top_level_compound",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]

        # AND condition at top level creates proper branching:
        # 1 success (IF: both conditions met)
        # 2 else (De Morgan: one fails for water, one fails for temp)
        assert len(root.children_ids) == 3

        if_branches = [
            tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].branch_condition.branch_type == "if"
        ]
        else_branches = [
            tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].branch_condition.branch_type == "else"
        ]

        assert len(if_branches) == 1
        assert len(else_branches) == 2
