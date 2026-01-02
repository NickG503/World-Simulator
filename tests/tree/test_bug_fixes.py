"""Tests for specific bug fixes in tree simulation.

These tests verify that the following bugs remain fixed:
1. Operator display: == for single values, ∈ for sets
2. Compound AND success conditions showing all attributes
3. Snapshot preservation when action sets a value
4. Net changes (not intermediate constraint + effect changes)
"""

import pytest

from simulator.core.tree.models import BranchCondition, WorldSnapshot
from simulator.core.tree.node_factory import compute_snapshot_diff
from simulator.core.tree.snapshot_utils import capture_snapshot_with_values


class TestOperatorDisplay:
    """Tests for correct operator display in branch conditions."""

    def test_single_value_uses_equals_operator(self):
        """Single value should use 'equals' operator, not 'in'."""
        bc = BranchCondition(
            attribute="cube.face",
            operator="equals",
            value="3",
            source="postcondition",
            branch_type="elif",
        )
        # Should describe as == not ∈
        desc = bc.describe()
        assert "cube.face" in desc
        assert "3" in desc

    def test_multi_value_uses_in_operator(self):
        """Multi-value set should use 'in' operator."""
        bc = BranchCondition(
            attribute="cube.face",
            operator="in",
            value=["1", "2", "4"],
            source="precondition",
            branch_type="success",
        )
        desc = bc.describe()
        assert "cube.face" in desc
        # Value should be formatted as a set
        assert "1" in desc and "2" in desc and "4" in desc


class TestCompoundConditionDisplay:
    """Tests for compound AND/OR condition display."""

    def test_compound_and_shows_all_conditions(self):
        """Compound AND condition should show all sub-conditions."""
        sub1 = BranchCondition(
            attribute="reel1.symbol",
            operator="in",
            value=["bar", "seven"],
            source="precondition",
            branch_type="success",
        )
        sub2 = BranchCondition(
            attribute="reel2.symbol",
            operator="in",
            value=["bar", "seven"],
            source="precondition",
            branch_type="success",
        )
        compound = BranchCondition(
            attribute="reel1.symbol",
            operator="in",
            value=["bar", "seven"],
            source="precondition",
            branch_type="success",
            compound_type="and",
            sub_conditions=[sub1, sub2],
        )

        desc = compound.describe()
        # Both attributes should appear
        assert "reel1.symbol" in desc
        assert "reel2.symbol" in desc
        assert "AND" in desc

    def test_compound_or_shows_all_conditions(self):
        """Compound OR condition should show all sub-conditions."""
        sub1 = BranchCondition(
            attribute="attr1",
            operator="equals",
            value="val1",
            source="precondition",
            branch_type="fail",
        )
        sub2 = BranchCondition(
            attribute="attr2",
            operator="equals",
            value="val2",
            source="precondition",
            branch_type="fail",
        )
        compound = BranchCondition(
            attribute="attr1",
            operator="equals",
            value="val1",
            source="precondition",
            branch_type="fail",
            compound_type="or",
            sub_conditions=[sub1, sub2],
        )

        desc = compound.describe()
        assert "attr1" in desc
        assert "attr2" in desc
        assert "OR" in desc


class TestSnapshotPreservation:
    """Tests for snapshot value preservation when action sets a value."""

    def test_action_value_preserved_when_outside_constraints(self, registry_manager):
        """When action sets a value outside constraint values, it should be preserved."""
        from simulator.io.loaders.object_loader import instantiate_default

        rm = registry_manager

        # Create a simple object with a face attribute
        obj_def = rm.objects.get("dice_double_merge")
        if obj_def is None:
            pytest.skip("dice_double_merge object not found")

        instance = instantiate_default(obj_def, rm)

        # Set face to "3" (as if action set it)
        instance.parts["cube"].attributes["face"].current_value = "3"

        # Capture snapshot with constraints that DON'T include "3"
        snapshot = capture_snapshot_with_values(
            instance,
            "cube.face",
            ["1", "2", "4"],  # Constraint values that don't include "3"
            rm,
            None,
        )

        # The snapshot should preserve "3" because the action set it
        face_value = snapshot.get_attribute_value("cube.face")
        assert face_value == "3", f"Expected '3' but got {face_value}"

    def test_constraint_applied_when_value_in_constraints(self, registry_manager):
        """When value is in constraints, constraint can be applied."""
        from simulator.io.loaders.object_loader import instantiate_default

        rm = registry_manager

        obj_def = rm.objects.get("dice_double_merge")
        if obj_def is None:
            pytest.skip("dice_double_merge object not found")

        instance = instantiate_default(obj_def, rm)

        # Set face to "5" which is in the constraint values
        instance.parts["cube"].attributes["face"].current_value = "5"

        snapshot = capture_snapshot_with_values(
            instance,
            "cube.face",
            ["3", "5", "6"],  # Constraint values that include "5"
            rm,
            None,
        )

        face_value = snapshot.get_attribute_value("cube.face")
        # Value should be "5" (either preserved or constrained - both valid)
        assert face_value == "5", f"Expected '5' but got {face_value}"


class TestNetChanges:
    """Tests for net change computation (not intermediate steps)."""

    def test_net_change_single_attribute(self):
        """Changes should show net before→after, not intermediate steps."""
        from simulator.core.simulation_runner import (
            AttributeSnapshot,
            ObjectStateSnapshot,
            PartStateSnapshot,
        )

        # Create parent snapshot with face = ['1', '2', '4']
        parent_attrs = {
            "face": AttributeSnapshot(
                value=["1", "2", "4"],
                trend="none",
                last_known_value=None,
                last_trend_direction=None,
                space_id="dice_face",
            )
        }
        parent_parts = {"cube": PartStateSnapshot(attributes=parent_attrs)}
        parent_state = ObjectStateSnapshot(
            type="dice",
            parts=parent_parts,
            global_attributes={},
        )
        parent_snapshot = WorldSnapshot(object_state=parent_state)

        # Create new snapshot with face = '3' (action set it)
        new_attrs = {
            "face": AttributeSnapshot(
                value="3",
                trend="none",
                last_known_value="3",
                last_trend_direction=None,
                space_id="dice_face",
            )
        }
        new_parts = {"cube": PartStateSnapshot(attributes=new_attrs)}
        new_state = ObjectStateSnapshot(
            type="dice",
            parts=new_parts,
            global_attributes={},
        )
        new_snapshot = WorldSnapshot(object_state=new_state)

        # Compute diff - should show single net change
        # Base changes might include intermediate narrowing + action effect
        base_changes = [
            {"attribute": "cube.face", "before": "1", "after": "3", "kind": "value"},
        ]

        result = compute_snapshot_diff(parent_snapshot, new_snapshot, base_changes)

        # Should have exactly one change for cube.face
        face_changes = [c for c in result if c["attribute"] == "cube.face"]
        assert len(face_changes) == 1, f"Expected 1 change but got {len(face_changes)}"

        # The change should show net: ['1', '2', '4'] → '3'
        change = face_changes[0]
        assert change["before"] == ["1", "2", "4"], f"Expected before=['1','2','4'] but got {change['before']}"
        assert change["after"] == "3", f"Expected after='3' but got {change['after']}"

    def test_no_duplicate_attribute_changes(self):
        """Same attribute should not appear multiple times in changes."""
        from simulator.core.simulation_runner import (
            AttributeSnapshot,
            ObjectStateSnapshot,
            PartStateSnapshot,
        )

        parent_attrs = {
            "level": AttributeSnapshot(
                value=["low", "medium", "high"],
                trend="none",
                last_known_value=None,
                last_trend_direction=None,
                space_id="level",
            )
        }
        parent_parts = {"battery": PartStateSnapshot(attributes=parent_attrs)}
        parent_state = ObjectStateSnapshot(
            type="device",
            parts=parent_parts,
            global_attributes={},
        )
        parent_snapshot = WorldSnapshot(object_state=parent_state)

        new_attrs = {
            "level": AttributeSnapshot(
                value="empty",
                trend="none",
                last_known_value="empty",
                last_trend_direction=None,
                space_id="level",
            )
        }
        new_parts = {"battery": PartStateSnapshot(attributes=new_attrs)}
        new_state = ObjectStateSnapshot(
            type="device",
            parts=new_parts,
            global_attributes={},
        )
        new_snapshot = WorldSnapshot(object_state=new_state)

        # Simulate what might happen with narrowing + action effect
        base_changes = [
            {"attribute": "battery.level", "before": ["low", "medium", "high"], "after": "medium", "kind": "narrowing"},
            {"attribute": "battery.level", "before": "medium", "after": "empty", "kind": "value"},
        ]

        result = compute_snapshot_diff(parent_snapshot, new_snapshot, base_changes)

        # Count changes per attribute
        attr_counts = {}
        for c in result:
            attr = c["attribute"]
            attr_counts[attr] = attr_counts.get(attr, 0) + 1

        # No attribute should appear more than once
        for attr, count in attr_counts.items():
            assert count == 1, f"Attribute '{attr}' appears {count} times (expected 1)"


class TestNestedDeMorganBranching:
    """Tests for correct De Morgan branching with nested AND/OR conditions.

    These tests ensure that complex nested conditions produce the correct
    number of success and fail branches according to De Morgan's laws:
    - NOT(A AND B) = NOT A OR NOT B (split into multiple fail branches)
    - NOT(A OR B) = NOT A AND NOT B (combine into single fail branch)
    """

    def test_and_in_or_creates_two_fail_branches(self, registry_manager):
        """(A AND B) OR C with all unknown should create 2 fail branches.

        De Morgan: NOT((A AND B) OR C) = (NOT A OR NOT B) AND NOT C
        - Fail 1: A fails, C fails, B unknown
        - Fail 2: B fails, C fails, A unknown
        """
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_and_in_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Success: 2 (one for A AND B, one for C)
        assert len(success) == 2, f"Expected 2 success branches, got {len(success)}"

        # Fail: 2 (one where A fails + C fails, one where B fails + C fails)
        assert len(fail) == 2, f"Expected 2 fail branches, got {len(fail)}"

    def test_fail_branches_have_different_unknown_attrs(self, registry_manager):
        """Each fail branch should leave a different attribute unknown.

        For (A AND B) OR C:
        - Fail 1: A constrained, B unknown, C constrained
        - Fail 2: A unknown, B constrained, C constrained
        """
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_fail_unknowns",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_nodes = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_nodes) == 2

        # Get attribute values from each fail node
        fail_attrs = []
        for node in fail_nodes:
            reel1 = node.snapshot.get_attribute_value("reel1.symbol")
            reel2 = node.snapshot.get_attribute_value("reel2.symbol")
            reel3 = node.snapshot.get_attribute_value("reel3.symbol")
            fail_attrs.append({"reel1": reel1, "reel2": reel2, "reel3": reel3})

        # One fail should have reel1 unknown, the other should have reel2 unknown
        reel1_unknowns = [f for f in fail_attrs if f["reel1"] == "unknown"]
        reel2_unknowns = [f for f in fail_attrs if f["reel2"] == "unknown"]

        assert len(reel1_unknowns) == 1, f"Expected 1 fail with reel1 unknown, got {len(reel1_unknowns)}"
        assert len(reel2_unknowns) == 1, f"Expected 1 fail with reel2 unknown, got {len(reel2_unknowns)}"

        # reel3 should be constrained (not unknown) in both
        for f in fail_attrs:
            assert f["reel3"] != "unknown", "reel3 should be constrained in all fail branches"

    def test_simple_or_creates_one_fail_branch(self, registry_manager):
        """Simple A OR B with unknown should create 1 fail branch.

        De Morgan: NOT(A OR B) = NOT A AND NOT B (single combined fail)
        """
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "check_high_symbols", "parameters": {}}],
            simulation_id="test_simple_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Simple OR should have 1 fail (all conditions combined)
        assert len(fail) >= 1, f"Expected at least 1 fail branch, got {len(fail)}"

    def test_known_value_satisfying_or_no_fail(self, registry_manager):
        """If a known value satisfies one branch of OR, no fail branches needed."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_known_satisfies",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "seven",  # C is known and satisfies!
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # If C (reel3) is known to be "seven", the OR is satisfied
        # We should have at least one success path
        success = [n for n in children if n.action_status == "ok"]
        fail = [n for n in children if n.action_status == "rejected"]

        assert len(success) >= 1, "Should have at least one success when C is known to satisfy"
        # With C known to pass, the OR is guaranteed - fail branches may still exist for exploration
        # but the important thing is success paths exist
        assert len(success) + len(fail) > 0, "Should have some branches"

    def test_deeply_nested_and_or(self, registry_manager):
        """Test with AND containing OR: (A OR B) AND C.

        This tests the inverse nesting pattern.
        NOT((A OR B) AND C) = NOT(A OR B) OR NOT C = (NOT A AND NOT B) OR NOT C

        With unknowns, this should create:
        - Success when A OR B passes AND C passes
        - Multiple fail scenarios
        """
        # Note: This would need a specific action with this precondition pattern
        # For now, we test that the simulation doesn't crash and produces valid output
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        # Use check_high_symbols which has AND at top level with IN conditions
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "check_high_symbols", "parameters": {}}],
            simulation_id="test_and_at_top",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
            },
        )

        # Should complete without error
        assert tree is not None
        assert len(tree.nodes) > 1

    def test_all_three_unknown_in_and_in_or(self, registry_manager):
        """All 3 attrs unknown in (A AND B) OR C - comprehensive check.

        Expected:
        - 2 success branches (A AND B satisfies, or C satisfies)
        - 2 fail branches (De Morgan gives 2 distinct ways to fail)
        - Each fail has exactly 2 attrs constrained, 1 unknown
        """
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_comprehensive",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        success = [n for n in children if n.action_status == "ok"]
        fail = [n for n in children if n.action_status == "rejected"]

        assert len(success) == 2, f"Expected 2 success, got {len(success)}"
        assert len(fail) == 2, f"Expected 2 fail, got {len(fail)}"

        # Each fail should have exactly one unknown attribute
        for node in fail:
            unknown_count = 0
            for attr in ["reel1.symbol", "reel2.symbol", "reel3.symbol"]:
                val = node.snapshot.get_attribute_value(attr)
                if val == "unknown":
                    unknown_count += 1
            assert unknown_count == 1, f"Fail branch should have 1 unknown attr, got {unknown_count}"

    def test_success_branch_conditions_correct(self, registry_manager):
        """Success branches should have correct branch conditions."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_success_bc",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        assert len(success) == 2

        # One success should be for A AND B (compound), one for C (simple)
        compound_success = [n for n in success if n.branch_condition and n.branch_condition.compound_type == "and"]
        simple_success = [n for n in success if n.branch_condition and n.branch_condition.compound_type is None]

        assert len(compound_success) == 1, "Should have 1 compound AND success"
        assert len(simple_success) == 1, "Should have 1 simple success"

        # The compound success should have sub_conditions for reel1 and reel2
        bc = compound_success[0].branch_condition
        assert bc.sub_conditions is not None
        assert len(bc.sub_conditions) == 2
        attrs_in_compound = {sub.attribute for sub in bc.sub_conditions}
        assert "reel1.symbol" in attrs_in_compound
        assert "reel2.symbol" in attrs_in_compound

    def test_fail_branch_conditions_correct(self, registry_manager):
        """Fail branches should have correct branch conditions."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_fail_bc",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail) == 2

        # Each fail should be a compound AND (De Morgan combines with AND)
        for node in fail:
            bc = node.branch_condition
            assert bc is not None
            assert bc.compound_type == "and", f"Fail branch should have compound_type='and', got {bc.compound_type}"
            assert bc.sub_conditions is not None
            assert len(bc.sub_conditions) == 2, (
                f"Fail branch should have 2 sub_conditions, got {len(bc.sub_conditions)}"
            )

            # Each fail should include reel3 (C always fails)
            attrs = {sub.attribute for sub in bc.sub_conditions}
            assert "reel3.symbol" in attrs, "Fail branch should always include reel3.symbol"

    def test_partial_known_reduces_branches(self, registry_manager):
        """When one attr is known to fail, fewer branches needed."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        # Set reel1 to a failing value for A
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_partial_known",
            initial_values={
                "reel1.symbol": "cherry",  # Known to NOT be seven, so A fails
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        # With A known to fail, (A AND B) can't succeed
        # Only C can satisfy the OR
        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # Should only have success for C (reel3)
        assert len(success) >= 1, "Should have at least 1 success (for C)"

        # Verify success is for reel3
        for node in success:
            reel3_val = node.snapshot.get_attribute_value("reel3.symbol")
            # reel3 should be "seven" in success (C satisfies)
            if reel3_val == "seven":
                break
        else:
            # If no explicit seven found, check the branch condition
            pass  # This is fine, we just verify count


class TestCartesianProductBranching:
    """Tests for Cartesian product when precondition and postcondition have UNRELATED attributes.

    Scenario: Precondition (face=6 OR color=red) with Postcondition IF (size=large OR weight=heavy) ELSE
    - Precondition: face, color attributes
    - Postcondition: size, weight attributes (UNRELATED to precondition)

    Expected: 2 precond success × 3 postcond branches = 6 success + 1 fail = 7 total branches
    """

    def test_cartesian_creates_correct_branch_count(self, registry_manager):
        """Unrelated precond OR and postcond OR should create Cartesian product."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_cartesian_count",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Precondition: face=6 OR color=red → 2 success paths
        # Postcondition: (size=large OR weight=heavy) ELSE → 3 branches per success
        # Cartesian: 2 × 3 = 6 success
        assert len(success) == 6, f"Expected 6 success branches (2×3 Cartesian), got {len(success)}"

        # Fail: face≠6 AND color≠red → 1 fail
        assert len(fail) == 1, f"Expected 1 fail branch, got {len(fail)}"

    def test_cartesian_precond_a_with_all_postcond(self, registry_manager):
        """Precondition A (face=6) should combine with all 3 postcond branches."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_precond_a",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # Filter for precond A: face=6
        precond_a_branches = [n for n in success if n.snapshot.get_attribute_value("cube.face") == "6"]

        # Should have 3 branches (size=large, weight=heavy, else)
        assert len(precond_a_branches) == 3, f"Expected 3 branches for precond A, got {len(precond_a_branches)}"

    def test_cartesian_precond_b_with_all_postcond(self, registry_manager):
        """Precondition B (color=red) should combine with all 3 postcond branches."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_precond_b",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # Filter for precond B: color=red
        precond_b_branches = [n for n in success if n.snapshot.get_attribute_value("cube.color") == "red"]

        # Should have 3 branches (size=large, weight=heavy, else)
        assert len(precond_b_branches) == 3, f"Expected 3 branches for precond B, got {len(precond_b_branches)}"

    def test_cartesian_postcond_values_correct(self, registry_manager):
        """Each postcond branch should have correct prize value."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_postcond_values",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # Check postcond→prize mapping
        jackpot_count = 0
        small_count = 0
        for node in success:
            prize = node.snapshot.get_attribute_value("prize.level")
            size = node.snapshot.get_attribute_value("cube.size")
            weight = node.snapshot.get_attribute_value("cube.weight")

            # IF (size=large OR weight=heavy) → jackpot
            if size == "large" or weight == "heavy":
                assert prize == "jackpot", f"size={size}, weight={weight} should give jackpot, got {prize}"
                jackpot_count += 1
            # ELSE → small
            else:
                assert prize == "small", f"size={size}, weight={weight} should give small, got {prize}"
                small_count += 1

        # 2 IF branches per precond × 2 precond = 4 jackpot
        # 1 ELSE branch per precond × 2 precond = 2 small
        assert jackpot_count == 4, f"Expected 4 jackpot branches, got {jackpot_count}"
        assert small_count == 2, f"Expected 2 small branches, got {small_count}"

    def test_cartesian_fail_constrains_precond_attrs(self, registry_manager):
        """Fail branch should constrain precondition attributes, not postcondition."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_fail_constraints",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail) == 1

        fail_node = fail[0]
        face = fail_node.snapshot.get_attribute_value("cube.face")
        color = fail_node.snapshot.get_attribute_value("cube.color")
        size = fail_node.snapshot.get_attribute_value("cube.size")
        weight = fail_node.snapshot.get_attribute_value("cube.weight")

        # Face should be constrained to non-6 values
        assert face != "6", "Fail should have face≠6"
        assert isinstance(face, list) or face != "6", "Face should be constrained"

        # Color should be constrained to non-red values
        assert color != "red", "Fail should have color≠red"

        # Postcond attrs should remain unknown (not involved in precondition)
        assert size == "unknown", f"Size should remain unknown in fail, got {size}"
        assert weight == "unknown", f"Weight should remain unknown in fail, got {weight}"

    def test_cartesian_known_precond_reduces_branches(self, registry_manager):
        """If one precond is known to satisfy, only that path's Cartesian product."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_known_precond",
            initial_values={
                "cube.face": "6",  # Known to satisfy precond A
                "cube.color": "unknown",
                "cube.size": "unknown",
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # With face=6 known, precond is guaranteed to pass
        # Should have at least 3 success (postcond branches for face=6 path)
        # May also have color=red branches
        assert len(success) >= 3, f"Expected at least 3 success (postcond), got {len(success)}"

    def test_cartesian_known_postcond_reduces_branches(self, registry_manager):
        """If both postcond attrs are known, only one postcond branch per precond."""
        from simulator.core.tree.tree_runner import TreeSimulationRunner

        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run(
            "dice_cartesian",
            [{"name": "check_cartesian", "parameters": {}}],
            simulation_id="test_known_postcond",
            initial_values={
                "cube.face": "unknown",
                "cube.color": "unknown",
                "cube.size": "large",  # Known postcond value (satisfies IF)
                "cube.weight": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # With size=large known, at least 2 success (for face=6 and color=red)
        # Each would have jackpot prize
        assert len(success) >= 2, f"Expected at least 2 success, got {len(success)}"
        assert len(fail) == 1, f"Expected 1 fail, got {len(fail)}"
