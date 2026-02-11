"""Question handling for tree simulation.

Provides the logic for asking the user questions to prune branches
when the tree becomes too wide, and propagating pruning through the tree.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from simulator.core.attributes import AttributePath
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.tree.models import SimulationTree, TreeNode

if TYPE_CHECKING:
    from simulator.core.registries.registry_manager import RegistryManager
    from simulator.core.tree.question_strategy import QuestionMetadata, QuestionStrategy

logger = logging.getLogger(__name__)


def check_and_ask_questions(
    tree: SimulationTree,
    leaves: List[Tuple[TreeNode, ObjectInstance]],
    object_type: str,
    registry_manager: "RegistryManager",
    strategy: "QuestionStrategy",
    question_callback: Callable[[str, List[str], "QuestionMetadata"], Optional[str]],
    action_name: str = "",
    action_index: int = 1,
    total_actions: int = 1,
    verbose: bool = False,
    max_questions: int = 5,
) -> List[Tuple[TreeNode, ObjectInstance]]:
    """Check if strategy says we should ask, and ask user questions to prune.

    Loops until the strategy says stop, no uncertain attributes remain,
    or max_questions rounds are reached.
    """
    from simulator.core.tree.question_strategy import QuestionContext, QuestionMetadata, count_active_leaves

    asked = 0
    while asked < max_questions:
        active_count = count_active_leaves(leaves)
        ctx = QuestionContext(
            active_leaf_count=active_count,
            total_node_count=len(tree.nodes),
            leaves=leaves,
            tree=tree,
            object_type=object_type,
            registry_manager=registry_manager,
        )

        if not strategy.should_ask(ctx):
            break

        result = strategy.select_attribute(ctx)
        if result is None:
            break

        attr_path, options = result

        metadata = QuestionMetadata(
            action_name=action_name,
            action_index=action_index,
            total_actions=total_actions,
            active_leaves=active_count,
        )
        answer = question_callback(attr_path, options, metadata)
        if answer is None:
            break

        if answer not in options:
            if verbose:
                logger.warning("Answer '%s' not in options %s, skipping", answer, options)
            break

        leaves = prune_leaves_by_answer(tree, leaves, attr_path, answer)
        asked += 1

        if verbose:
            remaining = count_active_leaves(leaves)
            logger.info("Question %d: %s = %s -> %d active leaves remaining", asked, attr_path, answer, remaining)

    return leaves


def prune_leaves_by_answer(
    tree: SimulationTree,
    leaves: List[Tuple[TreeNode, ObjectInstance]],
    attr_path: str,
    answer: str,
) -> List[Tuple[TreeNode, ObjectInstance]]:
    """Prune leaves incompatible with the user's answer, narrow compatible ones."""
    result: List[Tuple[TreeNode, ObjectInstance]] = []
    newly_pruned_ids: List[str] = []
    reason = f"User answered: {attr_path} = {answer}"

    for node, instance in leaves:
        if node.action_status != "ok" or node.pruned:
            result.append((node, instance))
            continue

        snapshot = node.snapshot
        value = snapshot.get_attribute_value(attr_path)

        if isinstance(value, list):
            if answer in value:
                narrowed = instance.deep_copy()
                parsed = AttributePath.parse(attr_path)
                parsed.set_value_in_instance(narrowed, answer)
                _clear_trend_on_instance(narrowed, attr_path)
                result.append((node, narrowed))
            else:
                tree.nodes[node.id].pruned = True
                tree.nodes[node.id].pruned_reason = reason
                newly_pruned_ids.append(node.id)
                result.append((node, instance))
        elif value is None or value == "unknown":
            narrowed = instance.deep_copy()
            parsed = AttributePath.parse(attr_path)
            parsed.set_value_in_instance(narrowed, answer)
            _clear_trend_on_instance(narrowed, attr_path)
            result.append((node, narrowed))
        elif value == answer:
            result.append((node, instance))
        else:
            tree.nodes[node.id].pruned = True
            tree.nodes[node.id].pruned_reason = reason
            newly_pruned_ids.append(node.id)
            result.append((node, instance))

    if newly_pruned_ids:
        propagate_pruning_upward(tree, newly_pruned_ids)

    return result


def propagate_pruning_upward(tree: SimulationTree, pruned_node_ids: List[str]) -> None:
    """Propagate pruning upward: if all children of a parent are pruned/failed, prune the parent too.

    Uses a bottom-up BFS from the newly pruned nodes toward the root.
    Never prunes the root node.
    """
    queue: deque = deque(pruned_node_ids)
    visited: set = set()

    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)

        node = tree.nodes.get(node_id)
        if not node:
            continue

        for parent_id in node.parent_ids:
            if parent_id in visited:
                continue
            parent = tree.nodes.get(parent_id)
            if not parent or parent.is_root or parent.pruned:
                continue

            all_children_dead = all(
                tree.nodes[cid].pruned or tree.nodes[cid].failed for cid in parent.children_ids if cid in tree.nodes
            )
            if all_children_dead:
                parent.pruned = True
                parent.pruned_reason = parent.pruned_reason or "All children pruned"
                queue.append(parent_id)


def _clear_trend_on_instance(instance: ObjectInstance, attr_path: str) -> None:
    """Clear the trend on an attribute in an ObjectInstance."""
    parsed = AttributePath.parse(attr_path)
    attr_inst = parsed.resolve_from_instance(instance)
    if attr_inst and hasattr(attr_inst, "trend"):
        attr_inst.trend = "none"
