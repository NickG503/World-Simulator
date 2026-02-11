"""
Tests for De Morgan's law in preconditions and postconditions.

Uses real-world objects:
- Coffee Machine: AND conditions (water >= low AND beans >= low AND temp == hot)
- Slot Machine: OR conditions (reel1 == seven OR reel2 == seven OR reel3 == seven)

Verifies:
- AND precondition: 1 success branch + N fail branches (De Morgan: NOT(A AND B) = NOT(A) OR NOT(B))
- OR precondition: N success branches + 1 fail branch (De Morgan: NOT(A OR B) = NOT(A) AND NOT(B))
"""

from simulator.core.tree.tree_runner import TreeSimulationRunner


class TestDeMorganPreconditions:
    """Tests for De Morgan's law in preconditions."""

    def test_and_precondition_with_two_unknowns(self, registry_manager):
        """Slot machine: AND precondition (check_jackpot) with 3 unknowns.

        check_jackpot requires: reel1 == seven AND reel2 == seven AND reel3 == seven
        De Morgan: NOT(A AND B AND C) = NOT(A) OR NOT(B) OR NOT(C) → 3 fail branches
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_jackpot", "parameters": {}}],
            simulation_id="test_and_demorgan_precond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Count success and fail branches (rejected = precondition failed)
        success_branches = [c for c in children if c.action_status == "ok"]
        fail_branches = [c for c in children if c.action_status == "rejected"]

        assert len(success_branches) == 1, "Should have exactly 1 success branch"
        assert len(fail_branches) >= 3, "De Morgan: NOT(A AND B AND C) → at least 3 fail branches"

        # Verify success branch has all conditions satisfied
        success = success_branches[0]
        reel1 = success.snapshot.get_attribute_value("reel1.symbol")
        reel2 = success.snapshot.get_attribute_value("reel2.symbol")
        reel3 = success.snapshot.get_attribute_value("reel3.symbol")

        assert reel1 == "seven", "Success: reel1 should be 'seven'"
        assert reel2 == "seven", "Success: reel2 should be 'seven'"
        assert reel3 == "seven", "Success: reel3 should be 'seven'"

    def test_or_precondition_with_two_unknowns(self, registry_manager):
        """Slot machine: OR precondition with 2 unknown reels creates 2 success + 1 fail.

        check_any_seven requires: reel1 == seven OR reel2 == seven OR reel3 == seven
        Testing with 2 reels unknown.
        De Morgan: NOT(A OR B) = NOT(A) AND NOT(B) → 1 fail branch
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_or_demorgan_precond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "bar",  # Known, not seven
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        success_branches = [c for c in children if c.action_status == "ok"]
        fail_branches = [c for c in children if c.action_status == "rejected"]

        # With 2 unknown reels, we should have 2 success (one per reel showing seven) + 1 fail
        assert len(success_branches) >= 2, "Should have at least 2 success branches (one per satisfied disjunct)"
        assert len(fail_branches) == 1, "De Morgan: NOT(A OR B) = NOT(A) AND NOT(B) → 1 fail branch"

        # Verify fail branch has BOTH reels NOT showing seven (De Morgan AND)
        fail_node = fail_branches[0]
        reel1 = fail_node.snapshot.get_attribute_value("reel1.symbol")
        reel2 = fail_node.snapshot.get_attribute_value("reel2.symbol")

        # Both should NOT be 'seven'
        if isinstance(reel1, list):
            assert "seven" not in reel1, "Fail: reel1 should NOT contain 'seven'"
        else:
            assert reel1 != "seven", "Fail: reel1 should not be 'seven'"

        if isinstance(reel2, list):
            assert "seven" not in reel2, "Fail: reel2 should NOT contain 'seven'"
        else:
            assert reel2 != "seven", "Fail: reel2 should not be 'seven'"


import pytest


class TestDeMorganPostconditions:
    """Tests for De Morgan's law in postconditions.

    NOTE: Compound condition branching in postconditions is not yet implemented.
    These tests document the expected behavior for future implementation.
    """

    @pytest.mark.skip(reason="Compound postcondition branching not yet implemented")
    def test_and_postcondition_with_two_unknowns(self, registry_manager):
        """Coffee machine: AND postcondition creates 1 THEN + 2 ELSE branches (De Morgan).

        check_ready: if (water_tank.level >= low AND heater.temperature == hot) then status.ready = on
        De Morgan ELSE: NOT(A AND B) = NOT(A) OR NOT(B) → 2 else branches
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_and_demorgan_postcond",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Should have 3 branches: 1 THEN + 2 ELSE (De Morgan)
        assert len(children) == 3, f"Expected 3 branches, got {len(children)}"

        # Identify THEN and ELSE branches by branch_condition
        then_branches = []
        else_branches = []
        for child in children:
            bc = child.branch_condition
            if bc and bc.branch_type == "if":
                then_branches.append(child)
            elif bc and bc.branch_type == "else":
                else_branches.append(child)

        assert len(then_branches) == 1, "Should have exactly 1 THEN branch"
        assert len(else_branches) == 2, "De Morgan: NOT(A AND B) → 2 ELSE branches"

        # Verify THEN branch: both conditions met, effect applied
        then_node = then_branches[0]
        water = then_node.snapshot.get_attribute_value("water_tank.level")
        temp = then_node.snapshot.get_attribute_value("heater.temperature")
        ready = then_node.snapshot.get_attribute_value("status.ready")

        # Water should be >= low (not empty)
        if isinstance(water, list):
            assert "empty" not in water, "THEN: water should not include 'empty'"
        else:
            assert water != "empty", "THEN: water should not be 'empty'"
        assert temp == "hot", "THEN: heater.temperature should be 'hot'"
        assert ready == "on", "THEN: status.ready should be set to 'on'"

        # Verify ELSE branches: one condition fails each, effect NOT applied
        for else_node in else_branches:
            ready = else_node.snapshot.get_attribute_value("status.ready")
            assert ready == "off", "ELSE: status.ready should remain 'off'"

    @pytest.mark.skip(reason="Compound postcondition branching not yet implemented")
    def test_or_postcondition_with_two_unknowns(self, registry_manager):
        """Slot machine: OR postcondition creates 2 THEN + 1 ELSE branch (De Morgan).

        award_prize: if (reel1 == seven OR reel2 == bar) then prize = small
        De Morgan ELSE: NOT(A OR B) = NOT(A) AND NOT(B) → 1 else branch
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "award_prize", "parameters": {}}],
            simulation_id="test_or_demorgan_postcond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Should have 3 branches: 2 THEN + 1 ELSE (De Morgan)
        assert len(children) == 3, f"Expected 3 branches, got {len(children)}"

        then_branches = []
        else_branches = []
        for child in children:
            bc = child.branch_condition
            if bc and bc.branch_type == "if":
                then_branches.append(child)
            elif bc and bc.branch_type == "else":
                else_branches.append(child)

        assert len(then_branches) == 2, "Should have 2 THEN branches (one per disjunct)"
        assert len(else_branches) == 1, "De Morgan: NOT(A OR B) → 1 ELSE branch"

        # Verify THEN branches: at least one condition met, effect applied
        for then_node in then_branches:
            prize = then_node.snapshot.get_attribute_value("display.prize")
            assert prize == "small", "THEN: display.prize should be 'small'"

        # Verify ELSE branch: BOTH conditions fail (De Morgan AND), effect NOT applied
        else_node = else_branches[0]
        reel1 = else_node.snapshot.get_attribute_value("reel1.symbol")
        reel2 = else_node.snapshot.get_attribute_value("reel2.symbol")
        prize = else_node.snapshot.get_attribute_value("display.prize")

        # reel1 should NOT be 'seven'
        if isinstance(reel1, list):
            assert "seven" not in reel1, "ELSE: reel1 should NOT contain 'seven'"
        else:
            assert reel1 != "seven", "ELSE: reel1 should not be 'seven'"

        # reel2 should NOT be 'bar'
        if isinstance(reel2, list):
            assert "bar" not in reel2, "ELSE: reel2 should NOT contain 'bar'"
        else:
            assert reel2 != "bar", "ELSE: reel2 should not be 'bar'"

        assert prize == "none", "ELSE: display.prize should remain 'none'"


class TestDeMorganComplex:
    """Tests for complex De Morgan scenarios with real-world objects."""

    def test_postcondition_else_branch_effects_not_applied(self, registry_manager):
        """Coffee machine: Verify ELSE branches don't apply the conditional effects."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_else_no_effect",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]

        for cid in root.children_ids:
            child = tree.nodes[cid]
            bc = child.branch_condition

            if bc and bc.branch_type == "else":
                # ELSE branches should NOT have status.ready set to 'on'
                ready = child.snapshot.get_attribute_value("status.ready")
                assert ready == "off", f"ELSE branch should not apply effect: ready={ready}"
            elif bc and bc.branch_type == "if":
                # IF (THEN) branch SHOULD have status.ready set to 'on'
                ready = child.snapshot.get_attribute_value("status.ready")
                assert ready == "on", f"IF branch should apply effect: ready={ready}"


class TestRecursiveDeMorgan:
    """Comprehensive tests for recursive De Morgan's law implementation."""

    def test_simple_and_demorgan(self, registry_manager):
        """Test: NOT(A AND B) = NOT(A) OR NOT(B) - creates multiple fail branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_simple_and",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "hot",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # AND with 2 unknowns should have: 1 success + 2 fail branches
        assert len(success_branches) == 1, f"Expected 1 success, got {len(success_branches)}"
        assert len(fail_branches) == 2, f"Expected 2 fail branches (De Morgan OR), got {len(fail_branches)}"

        # Each fail branch should be a simple condition (not compound)
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None
            assert bc.compound_type is None, "Simple fail branch should not be compound"

    def test_simple_or_demorgan(self, registry_manager):
        """Test: NOT(A OR B OR C) = NOT(A) AND NOT(B) AND NOT(C) - single fail branch."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_simple_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # OR with 3 unknowns should have: 3 success + 1 fail branch
        assert len(success_branches) == 3, f"Expected 3 success, got {len(success_branches)}"
        assert len(fail_branches) == 1, f"Expected 1 fail branch (De Morgan AND), got {len(fail_branches)}"

        # The fail branch should be a compound AND
        fb = fail_branches[0]
        bc = fb.branch_condition
        assert bc is not None
        assert bc.compound_type == "and", f"Expected compound AND, got {bc.compound_type}"
        assert len(bc.sub_conditions) == 3, f"Expected 3 sub-conditions, got {len(bc.sub_conditions)}"

    def test_nested_and_inside_or_demorgan(self, registry_manager):
        """Test: NOT((A AND B) OR C) = (NOT(A) OR NOT(B)) AND NOT(C).

        For nested (A AND B) OR C:
        - The outer OR creates a compound fail branch using De Morgan
        - NOT(A OR B) = NOT A AND NOT B, applied to the disjuncts
        - Creates 1 fail branch where all disjuncts fail
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_nested_and_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # For outer OR, De Morgan creates 1 fail branch (all disjuncts fail)
        # The inner AND's failure is represented by constraining its attributes
        assert len(fail_branches) >= 1, f"Expected at least 1 fail branch, got {len(fail_branches)}"

        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None

            # OR should never appear in branch conditions - OR means split
            assert bc.compound_type != "or", "OR should not appear in branch conditions"

            # At least one reel should fail (not be seven)
            reel1_val = fb.snapshot.get_attribute_value("reel1.symbol")
            reel3_val = fb.snapshot.get_attribute_value("reel3.symbol")
            has_fail = False
            if isinstance(reel1_val, list) and "seven" not in reel1_val:
                has_fail = True
            if isinstance(reel3_val, list) and "seven" not in reel3_val:
                has_fail = True
            assert has_fail, "Fail branch should constrain at least one reel to non-seven"

    def test_demorgan_with_known_values(self, registry_manager):
        """Test De Morgan when some values are already known."""
        runner = TreeSimulationRunner(registry_manager)

        # Set heater.temperature to known value that satisfies the condition
        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_demorgan_known",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "hot",  # Known value that satisfies
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Since heater.temperature is known and satisfies, we only have 2 fail branches
        # (for water_tank.level and bean_hopper.amount)
        assert len(fail_branches) == 2, f"Expected 2 fail branches, got {len(fail_branches)}"

        # None of the fail branches should mention heater.temperature
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None
            assert "heater" not in bc.attribute, f"Known attribute should not be in fail branch: {bc.attribute}"

    def test_demorgan_branch_values_are_complements(self, registry_manager):
        """Test that fail branch values are correct complements."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_complement_values",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_branches) == 1
        fb = fail_branches[0]

        # Check snapshot values - all reels should NOT contain "seven"
        for reel in ["reel1", "reel2", "reel3"]:
            val = fb.snapshot.get_attribute_value(f"{reel}.symbol")
            if isinstance(val, list):
                assert "seven" not in val, f"{reel} should not contain 'seven': {val}"
            else:
                assert val != "seven", f"{reel} should not be 'seven': {val}"

    def test_success_branch_count_for_nested_or(self, registry_manager):
        """Test that nested OR creates correct number of success branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_nested_success",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # For ((A AND B) OR C), we should have success branches for:
        # - (A AND B) both satisfied (from inner AND - creates 1 branch)
        # - C satisfied (from outer OR - creates 1 branch)
        # Total: 2 success branches (AND creates single branch, not separate)
        assert len(success_branches) == 2, f"Expected 2 success branches, got {len(success_branches)}"

    def test_all_branches_have_valid_snapshots(self, registry_manager):
        """Test that all branches (success and fail) have valid snapshots."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_valid_snapshots",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        for nid, node in tree.nodes.items():
            if nid == "state0":
                continue

            assert node.snapshot is not None, f"Node {nid} should have a snapshot"

            # All reel values should be valid (either known or a list of valid values)
            for reel in ["reel1", "reel2", "reel3"]:
                val = node.snapshot.get_attribute_value(f"{reel}.symbol")
                valid_symbols = ["cherry", "lemon", "bar", "bell", "seven"]

                if isinstance(val, list):
                    for v in val:
                        assert v in valid_symbols, f"Invalid value {v} in {reel} for node {nid}"
                elif val != "unknown":
                    assert val in valid_symbols, f"Invalid value {val} in {reel} for node {nid}"

    def test_demorgan_preserves_operator(self, registry_manager):
        """Test that De Morgan preserves correct operators (in/equals)."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_operators",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_branches) == 1
        fb = fail_branches[0]
        bc = fb.branch_condition

        # Check that operators are correct
        for sub in bc.sub_conditions:
            # Multiple values should use "in", single value should use "equals"
            if isinstance(sub.value, list) and len(sub.value) > 1:
                assert sub.operator == "in", f"Expected 'in' operator for list, got {sub.operator}"
            elif isinstance(sub.value, str):
                assert sub.operator == "equals", f"Expected 'equals' operator for string, got {sub.operator}"


# =============================================================================
# Edge Case Tests (merged from test_phase2_demorgan_edge_cases.py)
# =============================================================================


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
        # Fail: 2 (De Morgan: NOT((A AND B) OR C) = (NOT A OR NOT B) AND NOT C)
        #   - One fail where A fails + C fails (B unknown)
        #   - One fail where B fails + C fails (A unknown)
        assert len(success) == 2, f"Expected 2 success, got {len(success)}"
        assert len(fail) == 2, f"Expected 2 fail, got {len(fail)}"

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
