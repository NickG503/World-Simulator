"""
Node factory for tree simulation.

This module provides functions for creating and merging TreeNode objects,
including the DAG deduplication logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.tree.models import (
    BranchCondition,
    IncomingEdge,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)


def create_or_merge_node(
    tree: SimulationTree,
    parent_node: TreeNode,
    snapshot: WorldSnapshot,
    action_name: str,
    parameters: Dict[str, str],
    status: str,
    error: Optional[str],
    branch_condition: Optional[BranchCondition],
    base_changes: List[Dict[str, Any]],
    result_instance: Optional[ObjectInstance],
    layer_state_cache: Dict[str, Tuple[TreeNode, ObjectInstance]],
) -> TreeNode:
    """
    Create a new node or merge with existing if same state exists in cache.

    This is the unified entry point for all node creation, handling:
    - State hash computation
    - Cache lookup for deduplication
    - IncomingEdge creation for merged nodes
    - TreeNode creation for new nodes
    - Full diff computation including value set narrowing

    Args:
        tree: Simulation tree
        parent_node: Parent node
        snapshot: World snapshot for this node
        action_name: Name of action that led here
        parameters: Action parameters
        status: Action status (ok, rejected, constraint_violated, error)
        error: Error message if any
        branch_condition: Branch condition if any
        base_changes: Base changes from transition engine
        result_instance: Object instance after action (None for failed actions)
        layer_state_cache: Cache for deduplication

    Returns:
        The node (new or existing merged)
    """
    # Compute full changes including value set narrowing
    full_changes = compute_snapshot_diff(parent_node.snapshot, snapshot, base_changes)

    # Check for duplicate state in cache
    state_hash = snapshot.state_hash()
    if state_hash in layer_state_cache:
        existing_node, _ = layer_state_cache[state_hash]
        # Merge: add incoming edge to existing node
        edge = IncomingEdge(
            parent_id=parent_node.id,
            action_name=action_name,
            action_parameters=parameters,
            action_status=status,
            action_error=error,
            branch_condition=branch_condition,
            changes=full_changes,
        )
        tree.add_edge_to_existing_node(existing_node.id, parent_node.id, edge)
        return existing_node

    # Create new node
    node = TreeNode(
        id=tree.generate_node_id(),
        snapshot=snapshot,
        parent_ids=[parent_node.id],
        action_name=action_name,
        action_parameters=parameters,
        action_status=status,
        action_error=error,
        branch_condition=branch_condition,
        changes=full_changes,
    )
    layer_state_cache[state_hash] = (node, result_instance)
    return node


def create_root_node(
    tree: SimulationTree,
    snapshot: WorldSnapshot,
) -> TreeNode:
    """Create the root node with initial state."""
    return TreeNode(
        id=tree.generate_node_id(),  # state0
        snapshot=snapshot,
        action_name=None,  # Root has no action
    )


def create_error_node(
    tree: SimulationTree,
    parent_node: TreeNode,
    snapshot: WorldSnapshot,
    action_name: str,
    parameters: Dict[str, str],
    error: str,
) -> TreeNode:
    """Create an error node for action failures."""
    return TreeNode(
        id=tree.generate_node_id(),
        snapshot=snapshot,
        parent_ids=[parent_node.id],
        action_name=action_name,
        action_parameters=parameters,
        action_status=NodeStatus.ERROR.value,
        action_error=error,
    )


def compute_snapshot_diff(
    parent_snapshot: WorldSnapshot,
    new_snapshot: WorldSnapshot,
    base_changes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compute all changes between parent and new snapshot, including value set narrowing.

    This augments the base_changes (from the transition engine) with any additional
    changes due to value sets being narrowed to single values.

    Args:
        parent_snapshot: The parent node's snapshot (may have value sets)
        new_snapshot: The new node's snapshot (after action applied)
        base_changes: Changes already computed by the transition engine

    Returns:
        Complete list of changes including value set narrowing
    """
    # Get attributes already in base_changes
    changed_attrs = {c["attribute"] for c in base_changes if "attribute" in c}

    # Check all attributes for value set narrowing
    additional_changes = []
    for attr_path in parent_snapshot.get_all_attribute_paths():
        if attr_path in changed_attrs:
            continue  # Already tracked

        parent_value = parent_snapshot.get_attribute_value(attr_path)
        new_value = new_snapshot.get_attribute_value(attr_path)

        # Check if value set narrowed to single value
        if isinstance(parent_value, list) and not isinstance(new_value, list):
            if new_value != parent_value:
                additional_changes.append(
                    {
                        "attribute": attr_path,
                        "before": parent_value,
                        "after": new_value,
                        "kind": "value",
                    }
                )
        elif parent_value != new_value:
            # Any other difference
            additional_changes.append(
                {
                    "attribute": attr_path,
                    "before": parent_value,
                    "after": new_value,
                    "kind": "value",
                }
            )

    return additional_changes + base_changes


def compute_narrowing_change(
    parent_snapshot: WorldSnapshot,
    attr_path: str,
    new_values: List[str],
) -> List[Dict[str, Any]]:
    """
    Compute change when a value set is narrowed.

    Args:
        parent_snapshot: Parent snapshot with potentially wider value set
        attr_path: Attribute path being narrowed
        new_values: The narrowed value(s)

    Returns:
        List with change dict if narrowing occurred, empty list otherwise
    """
    parent_value = parent_snapshot.get_attribute_value(attr_path)

    # Check if this is actually narrowing a value set
    if isinstance(parent_value, list):
        new_value = new_values[0] if len(new_values) == 1 else new_values
        if new_value != parent_value:
            return [
                {
                    "attribute": attr_path,
                    "before": parent_value,
                    "after": new_value,
                    "kind": "narrowing",
                }
            ]

    return []
