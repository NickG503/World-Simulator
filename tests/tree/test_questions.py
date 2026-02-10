"""
Tests for the question strategy feature.

Tests the interactive question-asking mechanism that prunes branches
when the tree grows beyond a configured threshold, using pluggable strategies.
"""

from typing import Dict, List, Optional

from simulator.core.tree import TreeSimulationRunner
from simulator.core.tree.question_strategy import (
    FirstUnknownScorer,
    LeafCountThresholdStrategy,
    MostDiverseScorer,
    UncertaintyRatioStrategy,
)

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

    def callback(attribute: str, options: List[str], metadata: object = None) -> Optional[str]:
        calls.append({"attribute": attribute, "options": options, "metadata": metadata})
        return answers.get(attribute)

    callback.calls = calls  # type: ignore[attr-defined]
    return callback


def make_always_skip_callback():
    """Create a callback that always skips (returns None)."""
    calls: List[dict] = []

    def callback(attribute: str, options: List[str], metadata: object = None) -> Optional[str]:
        calls.append({"attribute": attribute, "options": options, "metadata": metadata})
        return None

    callback.calls = calls  # type: ignore[attr-defined]
    return callback


# =============================================================================
# Tests: Threshold Strategy Detection
# =============================================================================


class TestThresholdDetection:
    """Tests that questions are asked only when the threshold is exceeded."""

    def test_no_question_when_strategy_not_set(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Without strategy, no questions are asked even with many branches."""
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_no_strategy",
            initial_values=flashlight_unknown,
        )
        assert len(tree.nodes) > 1

    def test_no_question_below_threshold(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With a very high threshold, no question is asked."""
        cb = make_always_skip_callback()
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_high_threshold",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(1000),
            question_callback=cb,
        )
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
            question_strategy=LeafCountThresholdStrategy(2),
            question_callback=cb,
        )
        assert len(cb.calls) > 0  # type: ignore[attr-defined]


# =============================================================================
# Tests: Attribute Identification
# =============================================================================


class TestAttributeIdentification:
    """Tests that the correct uncertain attribute is identified."""

    def test_battery_level_identified_with_diverse_scorer(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """With MostDiverseScorer, battery.level (5 distinct values) should be asked."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_attr_id",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )
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
            question_strategy=LeafCountThresholdStrategy(2),
            question_callback=cb,
        )
        battery_calls = [
            call
            for call in cb.calls
            if call["attribute"] == "battery.level"  # type: ignore[attr-defined]
        ]
        if battery_calls:
            options = battery_calls[0]["options"]
            valid_levels = {"empty", "low", "medium", "high", "full"}
            assert all(opt in valid_levels for opt in options)
            assert len(options) >= 2


# =============================================================================
# Tests: Pruning
# =============================================================================


class TestPruning:
    """Tests that pruning correctly marks and filters nodes."""

    def test_pruning_reduces_node_count(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Answering a question should result in fewer active (non-pruned) nodes."""
        cb_answer = make_answer_callback({"battery.level": "medium"})
        tree_pruned = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}, {"name": "shake", "parameters": {}}],
            simulation_id="test_prune_reduce",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(3, scorer=MostDiverseScorer()),
            question_callback=cb_answer,
        )

        tree_full = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}, {"name": "shake", "parameters": {}}],
            simulation_id="test_no_prune",
            initial_values=flashlight_unknown,
        )

        full_count = len(tree_full.nodes)
        pruned_active = sum(1 for n in tree_pruned.nodes.values() if not n.pruned)
        assert pruned_active < full_count

    def test_pruned_nodes_marked_correctly(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Pruned nodes should have pruned=True and a reason."""
        cb = make_answer_callback({"battery.level": "medium"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_prune_marks",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        pruned_nodes = [n for n in tree.nodes.values() if n.pruned]
        if len(cb.calls) > 0:  # type: ignore[attr-defined]
            assert len(pruned_nodes) > 0
            for node in pruned_nodes:
                assert node.pruned_reason is not None
                assert "battery.level" in node.pruned_reason or "All children pruned" in node.pruned_reason

    def test_pruned_nodes_not_expanded(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Pruned nodes should not have active children."""
        cb = make_answer_callback({"battery.level": "medium"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}, {"name": "shake", "parameters": {}}],
            simulation_id="test_prune_no_expand",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(3, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        for node in tree.nodes.values():
            if not node.pruned:
                continue
            if node.children_ids:
                for cid in node.children_ids:
                    child = tree.nodes[cid]
                    assert child.pruned or child.failed, f"Pruned node {node.id} has active child {cid}"


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
            question_strategy=LeafCountThresholdStrategy(2),
            question_callback=cb,
        )
        pruned_count = sum(1 for n in tree.nodes.values() if n.pruned)
        assert pruned_count == 0

    def test_no_callback_no_error(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With strategy but no callback, should run without error."""
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_no_cb",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2),
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
            [{"name": "turn_on", "parameters": {}}, {"name": "shake", "parameters": {}}],
            simulation_id="test_integration",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(3, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        assert len(tree.nodes) > 1
        pruned = [n for n in tree.nodes.values() if n.pruned]
        active_leaves = [n for n in tree.nodes.values() if n.is_leaf and not n.pruned and n.action_status == "ok"]
        assert len(pruned) > 0
        assert len(active_leaves) >= 1


# =============================================================================
# Tests: Upward Pruning Propagation
# =============================================================================


class TestUpwardPruningPropagation:
    """Tests that pruning propagates upward through the tree."""

    def test_pruning_propagates_upward(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """Intermediate nodes whose children are ALL pruned should also be pruned."""
        cb = make_answer_callback({"battery.level": "full"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_propagate_up",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        pruned_nodes = [n for n in tree.nodes.values() if n.pruned]
        assert len(pruned_nodes) > 0

        for node in pruned_nodes:
            if node.is_root:
                continue
            if node.children_ids:
                for cid in node.children_ids:
                    child = tree.nodes[cid]
                    assert child.pruned or child.failed, f"Pruned node {node.id} has active child {cid}"

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
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        for node in tree.nodes.values():
            if node.pruned or node.is_root:
                continue
            if node.children_ids:
                has_live_child = any(
                    not tree.nodes[cid].pruned and not tree.nodes[cid].failed
                    for cid in node.children_ids
                    if cid in tree.nodes
                )
                assert has_live_child, f"Active node {node.id} has no live children"

    def test_propagation_increases_pruned_count(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """With propagation, more nodes should be pruned than just the leaves."""
        cb = make_answer_callback({"battery.level": "full"})
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_propagate_count",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )

        pruned = [n for n in tree.nodes.values() if n.pruned]
        leaf_pruned = [n for n in pruned if len(n.children_ids) == 0]
        parent_pruned = [n for n in pruned if len(n.children_ids) > 0]
        assert len(leaf_pruned) > 0, "Should have pruned leaf nodes"
        assert len(parent_pruned) > 0, "Propagation should have pruned parent nodes too"


# =============================================================================
# Tests: Strategy Pattern
# =============================================================================


class TestStrategyPattern:
    """Tests for the pluggable strategy architecture."""

    def test_uncertainty_ratio_strategy_triggers(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """UncertaintyRatioStrategy with low ratio should trigger questions."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_ratio_trigger",
            initial_values=flashlight_unknown,
            question_strategy=UncertaintyRatioStrategy(0.1),
            question_callback=cb,
        )
        # With 5 battery levels across 5 leaves, ratio = 5/5 = 1.0 > 0.1
        assert len(cb.calls) > 0  # type: ignore[attr-defined]

    def test_uncertainty_ratio_strategy_no_trigger(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """UncertaintyRatioStrategy with very high ratio should not trigger."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_ratio_no_trigger",
            initial_values=flashlight_unknown,
            question_strategy=UncertaintyRatioStrategy(100.0),
            question_callback=cb,
        )
        assert len(cb.calls) == 0  # type: ignore[attr-defined]

    def test_most_diverse_scorer_picks_battery(self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]):
        """MostDiverseScorer should pick battery.level (5 distinct values)."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_diverse_scorer",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=MostDiverseScorer()),
            question_callback=cb,
        )
        if cb.calls:  # type: ignore[attr-defined]
            # battery.level should be the most diverse attribute
            assert cb.calls[0]["attribute"] == "battery.level"  # type: ignore[attr-defined]

    def test_first_unknown_scorer_picks_something(
        self, runner: TreeSimulationRunner, flashlight_unknown: Dict[str, str]
    ):
        """FirstUnknownScorer should pick any uncertain attribute."""
        cb = make_always_skip_callback()
        runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="test_first_scorer",
            initial_values=flashlight_unknown,
            question_strategy=LeafCountThresholdStrategy(2, scorer=FirstUnknownScorer()),
            question_callback=cb,
        )
        # Should have asked about something
        assert len(cb.calls) > 0  # type: ignore[attr-defined]
        assert cb.calls[0]["attribute"] is not None  # type: ignore[attr-defined]
