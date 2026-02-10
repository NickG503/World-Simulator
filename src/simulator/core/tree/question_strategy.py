"""Pluggable strategy for interactive question-asking during simulation.

This module defines the Strategy pattern for two decisions:
1. should_ask() — Should we ask the user a question at this point?
2. select_attribute() — Which attribute to ask about and what are the options?

Both decisions are independently overridable via subclassing.

The attribute selection is further decomposed into an AttributeScorer that
ranks uncertain attributes. The highest-scoring attribute is selected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.registries.registry_manager import RegistryManager
    from simulator.core.tree.models import SimulationTree, TreeNode, WorldSnapshot


# =============================================================================
# Context: data bag passed to strategies
# =============================================================================


@dataclass
class QuestionContext:
    """All data a strategy needs to make decisions.

    This decouples strategies from the runner — strategies never
    import or reference TreeSimulationRunner.
    """

    active_leaf_count: int
    total_node_count: int
    leaves: List[Tuple[TreeNode, ObjectInstance]]
    tree: SimulationTree
    object_type: str
    registry_manager: RegistryManager


# =============================================================================
# AttributeScorer: ranks uncertain attributes
# =============================================================================


class AttributeScorer(ABC):
    """Scores uncertain attributes to decide which one to ask about.

    Higher score = we prefer to ask about this attribute first.
    """

    @abstractmethod
    def score(self, attr_path: str, distinct_values: Set[str], ctx: QuestionContext) -> float:
        """Score an uncertain attribute.

        Args:
            attr_path: The attribute path (e.g., 'battery.level').
            distinct_values: The set of distinct values for this attribute
                             across all active leaves.
            ctx: The full question context.

        Returns:
            A numeric score. The attribute with the highest score is selected.
        """
        ...


class FirstUnknownScorer(AttributeScorer):
    """Default scorer: returns 1.0 for every uncertain attribute.

    Since all scores are equal, the first uncertain attribute encountered
    (in iteration order) wins. Simple and fast.
    """

    def score(self, attr_path: str, distinct_values: Set[str], ctx: QuestionContext) -> float:
        return 1.0


class MostDiverseScorer(AttributeScorer):
    """Scores by the number of distinct values across leaves.

    An attribute with 5 distinct values scores higher than one with 2.
    This was the original hardcoded behavior.
    """

    def score(self, attr_path: str, distinct_values: Set[str], ctx: QuestionContext) -> float:
        return float(len(distinct_values))


# =============================================================================
# Helpers: shared logic for attribute analysis
# =============================================================================


def get_uncertain_attributes(
    ctx: QuestionContext,
) -> Dict[str, Set[str]]:
    """Collect all uncertain attributes and their distinct values across active leaves.

    An attribute is uncertain if it has >1 distinct value or contains 'unknown'.

    Returns:
        Dict mapping attr_path -> set of distinct values.
    """
    attr_distinct: Dict[str, Set[str]] = {}

    for node, _ in ctx.leaves:
        if node.action_status != "ok" or node.pruned:
            continue

        snapshot = node.snapshot
        for attr_path in snapshot.get_all_attribute_paths():
            value = snapshot.get_attribute_value(attr_path)
            if attr_path not in attr_distinct:
                attr_distinct[attr_path] = set()

            if isinstance(value, list):
                attr_distinct[attr_path].update(value)
            elif value is None or value == "unknown":
                attr_distinct[attr_path].add("__unknown__")
            elif value is not None:
                attr_distinct[attr_path].add(value)

    # Filter to only uncertain attributes
    return {path: vals for path, vals in attr_distinct.items() if len(vals) > 1 or "__unknown__" in vals}


def collect_attribute_options(
    ctx: QuestionContext,
    attr_path: str,
) -> List[str]:
    """Collect all possible values for an attribute across active leaves.

    For 'unknown' values, expands to the full qualitative space.
    Returns a sorted list (by space order if available).
    """
    options: set = set()

    for node, _ in ctx.leaves:
        if node.action_status != "ok" or node.pruned:
            continue

        snapshot = node.snapshot
        value = snapshot.get_attribute_value(attr_path)

        if isinstance(value, list):
            options.update(value)
        elif value is None or value == "unknown":
            space_values = _get_space_values(snapshot, attr_path, ctx.registry_manager)
            if space_values:
                options.update(space_values)
            else:
                options.add("unknown")
        else:
            options.add(value)

    # Sort by space order if available
    space_order = _get_space_order(ctx.leaves, attr_path, ctx.registry_manager)
    if space_order:
        ordered = [v for v in space_order if v in options]
        remaining = sorted(v for v in options if v not in space_order)
        return ordered + remaining

    return sorted(options)


def _get_space_values(
    snapshot: WorldSnapshot,
    attr_path: str,
    registry_manager: RegistryManager,
) -> Optional[List[str]]:
    """Get all values from an attribute's qualitative space."""
    attr_snap = snapshot._get_attribute_snapshot(attr_path)
    if attr_snap and attr_snap.space_id:
        try:
            space = registry_manager.spaces.get(attr_snap.space_id)
            return list(space.levels)
        except Exception:
            pass
    return None


def _get_space_order(
    leaves: List[Tuple[TreeNode, ObjectInstance]],
    attr_path: str,
    registry_manager: RegistryManager,
) -> Optional[List[str]]:
    """Get the ordered levels from the qualitative space for sorting."""
    for node, _ in leaves:
        attr_snap = node.snapshot._get_attribute_snapshot(attr_path)
        if attr_snap and attr_snap.space_id:
            try:
                space = registry_manager.spaces.get(attr_snap.space_id)
                return list(space.levels)
            except Exception:
                pass
    return None


def count_active_leaves(
    leaves: List[Tuple[TreeNode, ObjectInstance]],
) -> int:
    """Count non-failed, non-pruned leaves."""
    return sum(1 for node, _ in leaves if node.action_status == "ok" and not node.pruned)


# =============================================================================
# QuestionStrategy: base class + concrete implementations
# =============================================================================


class QuestionStrategy(ABC):
    """Base class for question-asking strategies.

    Subclasses must implement should_ask(). The select_attribute() method
    has a default implementation that uses an AttributeScorer to pick
    the best uncertain attribute.

    Args:
        scorer: AttributeScorer to rank uncertain attributes.
                Defaults to MostDiverseScorer (picks the attribute with the
                most distinct values, i.e., the root cause of branching).
    """

    def __init__(self, scorer: Optional[AttributeScorer] = None):
        self.scorer = scorer or MostDiverseScorer()

    @abstractmethod
    def should_ask(self, ctx: QuestionContext) -> bool:
        """Return True if we should ask the user a question now."""
        ...

    def select_attribute(self, ctx: QuestionContext) -> Optional[Tuple[str, List[str]]]:
        """Select which attribute to ask about.

        Default: find all uncertain attributes, score them with self.scorer,
        pick the highest-scoring one, then collect its options.

        Returns:
            (attribute_path, sorted_options) or None if nothing to ask.
        """
        uncertain = get_uncertain_attributes(ctx)
        if not uncertain:
            return None

        # Score each uncertain attribute and pick the best
        best_attr = max(
            uncertain.keys(),
            key=lambda p: self.scorer.score(p, uncertain[p], ctx),
        )

        options = collect_attribute_options(ctx, best_attr)
        if len(options) <= 1:
            return None

        return best_attr, options


class LeafCountThresholdStrategy(QuestionStrategy):
    """Ask when the active leaf count exceeds a fixed threshold.

    This reproduces the original --ask-threshold behavior.
    """

    def __init__(self, threshold: int = 999, scorer: Optional[AttributeScorer] = None):
        super().__init__(scorer)
        self.threshold = threshold

    def should_ask(self, ctx: QuestionContext) -> bool:
        return ctx.active_leaf_count > self.threshold


class UncertaintyRatioStrategy(QuestionStrategy):
    """Ask when value diversity exceeds a ratio of active leaves.

    For the most uncertain attribute, computes:
        distinct_values / active_leaf_count

    If this ratio exceeds the configured threshold, asks a question.
    Default ratio is 0.25 (ask if >25% of leaves disagree on a value).
    """

    def __init__(self, ratio: float = 0.25, scorer: Optional[AttributeScorer] = None):
        super().__init__(scorer)
        self.ratio = ratio

    def should_ask(self, ctx: QuestionContext) -> bool:
        if ctx.active_leaf_count <= 1:
            return False

        uncertain = get_uncertain_attributes(ctx)
        if not uncertain:
            return False

        max_distinct = max(len(vals) for vals in uncertain.values())
        return (max_distinct / ctx.active_leaf_count) > self.ratio


__all__ = [
    "AttributeScorer",
    "FirstUnknownScorer",
    "LeafCountThresholdStrategy",
    "MostDiverseScorer",
    "QuestionContext",
    "QuestionStrategy",
    "UncertaintyRatioStrategy",
    "collect_attribute_options",
    "count_active_leaves",
    "get_uncertain_attributes",
]
