"""
Tests for the ASK_QUESTION_THRESHOLD feature.

Tests the interactive question-asking mechanism that prunes branches
when the tree grows beyond a configured threshold.
"""

from typing import Dict, List, Optional

from simulator.core.tree import TreeSimulationRunner

# =============================================================================
# Mock Callbacks
# =============================================================================


def make_answer_callback(answers: Dict[str, str]):
    """Create a callback that returns pre-configured answers.

    Args:
        answers: Dict mapping attribute_path -> answer value.
                 If the attribute is not in the dict, returns None (skip).
    """
    calls: List[dict] = []

    def callback(attribute: str, options: List[str]) -> Optional[str]:
        calls.append({"attribute": attribute, "options": options})
        return answers.get(attribute)

    callback.calls = calls  # type: ignore[attr-defined]
    return callback


def make_always_skip_callback():
    """Create a callback that always skips (returns None)."""
    calls: List[dict] = []

    def callback(attribute: str, options: List[str]) -> Optional[str]:
        calls.append({"attribute": attribute, "options": options})
        return None

    callback.calls = calls  # type: ignore[attr-defined]
    return callback


# =============================================================================
# Tests: Threshold Detection
# =============================================================================


class TestThresholdDetection:
    """Tests that questions are asked only when the threshold is exceeded."""

    def test_no_question_when_threshold_not_set(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Without threshold, no questions are asked even with many branches."""
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_no_threshold",
            initial_values=flashlight_unknown,
        )
        # Should run normally, producing branches
        assert len(tree.nodes) > 1

    def test_no_question_below_threshold(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With a very high threshold, no question is asked."""
        cb = make_always_skip_callback()
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_high_threshold",
            initial_values=flashlight_unknown,
            ask_question_threshold=1000,
            question_callback=cb,
        )
        # Callback should never be called
        assert len(cb.calls) == 0  # type: ignore[attr-defined]
        assert len(tree.nodes) > 1

    def test_question_asked_above_threshold(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With a low threshold, a question is asked."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_low_threshold",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )
        # Callback should have been called at least once
        assert len(cb.calls) > 0  # type: ignore[attr-defined]


# =============================================================================
# Tests: Attribute Identification
# =============================================================================


class TestAttributeIdentification:
    """Tests that the correct uncertain attribute is identified."""

    def test_battery_level_identified_for_flashlight(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """For flashlight with unknown battery, battery.level should be asked."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_attr_id",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )
        # At least one call should be about battery.level
        asked_attrs = [call["attribute"] for call in cb.calls]  # type: ignore[attr-defined]
        assert "battery.level" in asked_attrs


# =============================================================================
# Tests: Option Collection
# =============================================================================


class TestOptionCollection:
    """Tests that the correct set of options is collected."""

    def test_options_are_valid_battery_levels(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Options for battery.level should be valid space values."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_options",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )
        # Find the battery.level call
        battery_calls = [
            call
            for call in cb.calls  # type: ignore[attr-defined]
            if call["attribute"] == "battery.level"
        ]
        if battery_calls:
            options = battery_calls[0]["options"]
            # Battery levels should be from the space
            valid_levels = {"empty", "low", "medium", "high", "full"}
            assert all(opt in valid_levels for opt in options)
            assert len(options) >= 2  # At least 2 options to be meaningful


# =============================================================================
# Tests: Pruning
# =============================================================================


class TestPruning:
    """Tests that pruning correctly marks and filters nodes."""

    def test_pruning_reduces_node_count(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Answering a question should result in fewer active (non-pruned) nodes
        when continuing to subsequent actions."""
        # Run WITH pruning (answer: medium)
        cb_answer = make_answer_callback({"battery.level": "medium"})
        tree_pruned = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "shake", "parameters": {}},
            ],
            simulation_id="test_prune_reduce",
            initial_values=flashlight_unknown,
            ask_question_threshold=3,
            question_callback=cb_answer,
        )

        # Run WITHOUT pruning
        tree_full = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "shake", "parameters": {}},
            ],
            simulation_id="test_no_prune",
            initial_values=flashlight_unknown,
        )

        # Pruned tree should have fewer total nodes (or same with some pruned)
        full_count = len(tree_full.nodes)
        pruned_active = sum(1 for n in tree_pruned.nodes.values() if not n.pruned)

        # The active count should be less than the full tree
        assert pruned_active < full_count

    def test_pruned_nodes_marked_correctly(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Pruned nodes should have pruned=True and a reason."""
        cb = make_answer_callback({"battery.level": "medium"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_prune_marks",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )

        pruned_nodes = [n for n in tree.nodes.values() if n.pruned]
        if len(cb.calls) > 0:  # type: ignore[attr-defined]
            # If a question was asked, some nodes should be pruned
            assert len(pruned_nodes) > 0
            for node in pruned_nodes:
                assert node.pruned_reason is not None
                # Direct pruning has "battery.level" in reason;
                # upward-propagated pruning has "All children pruned"
                assert "battery.level" in node.pruned_reason or "All children pruned" in node.pruned_reason

    def test_pruned_nodes_not_expanded(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Pruned nodes should not have children from subsequent actions."""
        cb = make_answer_callback({"battery.level": "medium"})
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "shake", "parameters": {}},
            ],
            simulation_id="test_prune_no_expand",
            initial_values=flashlight_unknown,
            ask_question_threshold=3,
            question_callback=cb,
        )

        pruned_nodes = [n for n in tree.nodes.values() if n.pruned]
        for node in pruned_nodes:
            if node.children_ids:
                # Pruned by upward propagation: all children must also be pruned/failed
                for cid in node.children_ids:
                    child = tree.nodes[cid]
                    assert child.pruned or child.failed, f"Pruned node {node.id} has active child {cid}"
            # Leaf-level pruned nodes have no children (they were pruned directly)


# =============================================================================
# Tests: Callback Behavior
# =============================================================================


class TestCallbackBehavior:
    """Tests for different callback behaviors."""

    def test_skip_callback_no_pruning(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """If callback returns None, no pruning should occur."""
        cb = make_always_skip_callback()
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_skip",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )
        pruned_count = sum(1 for n in tree.nodes.values() if n.pruned)
        assert pruned_count == 0

    def test_no_callback_no_error(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With threshold but no callback, should run without error."""
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_no_cb",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=None,
        )
        assert len(tree.nodes) > 1


# =============================================================================
# Tests: Integration with Multi-Action Simulation
# =============================================================================


class TestMultiActionIntegration:
    """Integration tests with multi-action simulations."""

    def test_flashlight_turn_on_shake_with_question(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """Full integration: flashlight with turn_on + shake and question."""
        cb = make_answer_callback({"battery.level": "high"})
        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "shake", "parameters": {}},
            ],
            simulation_id="test_integration",
            initial_values=flashlight_unknown,
            ask_question_threshold=3,
            question_callback=cb,
        )

        # Should complete without error
        assert len(tree.nodes) > 1

        # Some nodes should be pruned
        pruned = [n for n in tree.nodes.values() if n.pruned]
        active_leaves = [n for n in tree.nodes.values() if n.is_leaf and not n.pruned and n.action_status == "ok"]

        # After answering, should have significantly fewer active leaves
        assert len(pruned) > 0
        # Active leaves should exist (the simulation continued past the question)
        assert len(active_leaves) >= 1


# =============================================================================
# Tests: Upward Pruning Propagation
# =============================================================================


class TestUpwardPruningPropagation:
    """Tests that pruning propagates upward through the tree."""

    def test_pruning_propagates_upward(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Intermediate nodes (solver/time) whose children are ALL pruned
        should also be marked as pruned via bottom-up propagation."""
        cb = make_answer_callback({"battery.level": "full"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_propagate_up",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )

        pruned_nodes = [n for n in tree.nodes.values() if n.pruned]

        # There should be pruned nodes (leaves + propagated parents)
        assert len(pruned_nodes) > 0

        # Verify propagation: for every non-root pruned node, check that
        # it either was a leaf that got pruned directly, or all its children are pruned/failed
        for node in pruned_nodes:
            if node.is_root:
                continue
            if node.children_ids:
                # This node was pruned by propagation — all children must be pruned/failed
                for cid in node.children_ids:
                    child = tree.nodes[cid]
                    assert child.pruned or child.failed, f"Pruned node {node.id} has active child {cid}"

        # The root should never be pruned
        root = tree.nodes.get("state0")
        assert root is not None
        assert not root.pruned

    def test_propagation_stops_at_live_sibling(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Propagation should stop when a parent has at least one active child."""
        cb = make_answer_callback({"battery.level": "full"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_propagate_stop",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )

        # Find nodes that are NOT pruned and have children
        for node in tree.nodes.values():
            if node.pruned or node.is_root:
                continue
            if node.children_ids:
                # At least one child should be alive (not all pruned/failed)
                has_live_child = any(
                    not tree.nodes[cid].pruned and not tree.nodes[cid].failed
                    for cid in node.children_ids
                    if cid in tree.nodes
                )
                assert has_live_child, f"Active node {node.id} has no live children — should have been pruned"

    def test_propagation_increases_pruned_count(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With propagation, more nodes should be pruned than just the leaves."""
        cb = make_answer_callback({"battery.level": "full"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_propagate_count",
            initial_values=flashlight_unknown,
            ask_question_threshold=2,
            question_callback=cb,
        )

        pruned = [n for n in tree.nodes.values() if n.pruned]
        # The direct leaf pruning would only prune ~4 leaves (empty, low, medium, high)
        # With propagation, their solver and time parents should also be pruned
        # So total pruned should be significantly more than just the leaf count
        leaf_pruned = [n for n in pruned if len(n.children_ids) == 0]
        parent_pruned = [n for n in pruned if len(n.children_ids) > 0]

        # There should be BOTH pruned leaves AND pruned parent nodes
        assert len(leaf_pruned) > 0, "Should have pruned leaf nodes"
        assert len(parent_pruned) > 0, "Propagation should have pruned parent nodes too"
