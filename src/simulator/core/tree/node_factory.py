"""Node factory for tree simulation - creating and merging TreeNode objects."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.tree.models import (
    BranchCondition,
    IncomingEdge,
    NodeStatus,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.types import ChangeDict


def create_or_merge_node(
    tree: SimulationTree,
    parent_node: TreeNode,
    snapshot: WorldSnapshot,
    action_name: str,
    parameters: Dict[str, str],
    status: str,
    error: Optional[str],
    branch_condition: Optional[BranchCondition],
    base_changes: List[ChangeDict],
    result_instance: Optional[ObjectInstance],
    layer_state_cache: Dict[str, Tuple[TreeNode, ObjectInstance]],
) -> TreeNode:
    """Create a new node or merge with existing if same state found in cache."""
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
    base_changes: List[ChangeDict],
) -> List[ChangeDict]:
    """Compute changes between snapshots, including value set narrowing."""
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
) -> List[ChangeDict]:
    """Compute change when a value set is narrowed. Returns empty list if no narrowing."""
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
