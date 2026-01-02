"""
Tree-based simulation data models.

- WorldSnapshot: Immutable state of the world at a point in time
- BranchCondition: Describes what condition led to a specific branch
- TreeNode: A node in the simulation tree (represents a world state)
- SimulationTree: The complete tree/DAG structure with all nodes
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from simulator.core.simulation_runner import ObjectStateSnapshot


class NodeStatus(str, Enum):
    """Status of an action execution at a node."""

    OK = "ok"  # Action succeeded
    REJECTED = "rejected"  # Precondition failed
    CONSTRAINT_VIOLATED = "constraint_violated"  # Constraint check failed
    ERROR = "error"  # Action not found or other error


class WorldSnapshot(BaseModel):
    """
    Immutable state of the world at a point in time.

    This captures all attribute values, trends, and metadata for an object
    at a specific moment in the simulation.
    """

    object_state: ObjectStateSnapshot
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def get_attribute_value(self, path: str) -> Union[str, List[str], None]:
        """
        Get an attribute value by path.

        Args:
            path: Attribute path like 'battery.level' (part.attribute) or 'power' (global)

        Returns:
            The attribute value (string or list of values) or None if not found
        """
        attr = self._get_attribute_snapshot(path)
        return attr.value if attr else None

    def _get_attribute_snapshot(self, path: str):
        """
        Get the AttributeSnapshot for a given path.

        Args:
            path: Attribute path like 'battery.level' or 'power'

        Returns:
            AttributeSnapshot or None if not found
        """
        parts = path.split(".")

        if len(parts) == 1:
            # Global attribute
            return self.object_state.global_attributes.get(parts[0])
        elif len(parts) == 2:
            # Part attribute
            part = self.object_state.parts.get(parts[0])
            if part:
                return part.attributes.get(parts[1])
        return None

    def get_single_value(self, path: str) -> Optional[str]:
        """
        Get attribute value as a single string.

        If the value is a set, returns the first element.
        """
        attr = self._get_attribute_snapshot(path)
        if not attr:
            return None
        return attr.get_single_value()

    def get_attribute_trend(self, path: str) -> Optional[str]:
        """Get an attribute's trend by path."""
        parts = path.split(".")

        if len(parts) == 1:
            attr = self.object_state.global_attributes.get(parts[0])
            return attr.trend if attr else None
        elif len(parts) == 2:
            part = self.object_state.parts.get(parts[0])
            if part:
                attr = part.attributes.get(parts[1])
                return attr.trend if attr else None
        return None

    def is_attribute_known(self, path: str) -> bool:
        """
        Check if an attribute value is known (single definite value).

        In Phase 2, a value is "unknown" if:
        - It's None
        - It's the string "unknown"
        - It's a set with more than one value (uncertain state)

        This is used for branching decisions.
        """
        attr = self._get_attribute_snapshot(path)
        if not attr:
            return False
        return not attr.is_unknown()

    def is_attribute_value_set(self, path: str) -> bool:
        """Check if an attribute's value is a set of possible values."""
        attr = self._get_attribute_snapshot(path)
        return attr is not None and attr.is_value_set()

    def get_all_attribute_paths(self) -> List[str]:
        """Get all attribute paths in this snapshot."""
        paths = []

        # Part attributes
        for part_name, part in self.object_state.parts.items():
            for attr_name in part.attributes:
                paths.append(f"{part_name}.{attr_name}")

        # Global attributes
        for attr_name in self.object_state.global_attributes:
            paths.append(attr_name)

        return paths

    def state_hash(self) -> str:
        """
        Compute a canonical hash of the world state for deduplication.

        This creates a deterministic string representation of all attribute
        values and trends that can be used as a dictionary key.

        Excludes:
        - Timestamps (non-semantic metadata)
        - space_id (structural, not state)
        - last_known_value, last_trend_direction (historical, not current state)
        """
        import hashlib
        import json

        state_parts = []

        # Object type
        state_parts.append(f"type:{self.object_state.type}")

        # Process part attributes in sorted order for determinism
        for part_name in sorted(self.object_state.parts.keys()):
            part = self.object_state.parts[part_name]
            for attr_name in sorted(part.attributes.keys()):
                attr = part.attributes[attr_name]
                # Normalize value: convert list to sorted tuple for consistent hashing
                if isinstance(attr.value, list):
                    value_repr = json.dumps(sorted(attr.value))
                else:
                    value_repr = str(attr.value)
                trend = attr.trend or "none"
                state_parts.append(f"{part_name}.{attr_name}:{value_repr}:{trend}")

        # Process global attributes in sorted order
        for attr_name in sorted(self.object_state.global_attributes.keys()):
            attr = self.object_state.global_attributes[attr_name]
            if isinstance(attr.value, list):
                value_repr = json.dumps(sorted(attr.value))
            else:
                value_repr = str(attr.value)
            trend = attr.trend or "none"
            state_parts.append(f"global.{attr_name}:{value_repr}:{trend}")

        # Create deterministic string and hash it
        canonical = "|".join(state_parts)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class BranchCondition(BaseModel):
    """
    Describes the condition that led to this branch.

    This captures what decision was made to reach this node:
    - For precondition branches: whether the precondition passed or failed
    - For postcondition branches: which if/elif/else case was matched

    Supports both simple conditions and compound conditions (AND/OR).
    For compound conditions:
    - attribute may be a single attribute or unused (use sub_conditions instead)
    - compound_type indicates "and" or "or"
    - sub_conditions contains the individual BranchCondition entries

    For simple conditions:
    - attribute: the checked attribute path
    - operator: comparison operator
    - value: expected value(s)
    """

    attribute: str  # e.g., "battery.level" (may be empty for compound)
    operator: str  # e.g., "equals", "not_equals", "in" (may be empty for compound)
    value: Union[str, List[str]]  # Single value OR set of values (for else branch)
    source: Literal["precondition", "postcondition"]

    # For postcondition branches with if/elif/else
    branch_type: Literal["if", "elif", "else", "success", "fail"] = "if"

    # For compound conditions (AND/OR)
    compound_type: Optional[Literal["and", "or"]] = None
    sub_conditions: Optional[List["BranchCondition"]] = None

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        """Validate operator is supported."""
        valid_ops = {"equals", "not_equals", "lt", "lte", "gt", "gte", "in", "not_in", ""}
        # Also accept display forms
        if v in valid_ops or v.startswith("not "):
            return v
        return v

    def is_value_set(self) -> bool:
        """Check if the value is a set of possible values."""
        return isinstance(self.value, list)

    def is_compound(self) -> bool:
        """Check if this is a compound condition."""
        return self.compound_type is not None

    def get_value_display(self) -> str:
        """Get a display string for the value (handles sets)."""
        if isinstance(self.value, list):
            return "{" + ", ".join(self.value) + "}"
        return str(self.value)

    def describe(self) -> str:
        """Human-readable description of the branch condition."""
        from simulator.utils.error_formatting import get_operator_symbol

        if self.compound_type and self.sub_conditions:
            # Compound condition description
            parts = [sc.describe() for sc in self.sub_conditions]
            joiner = " AND " if self.compound_type == "and" else " OR "
            return "(" + joiner.join(parts) + ")"

        op_symbol = get_operator_symbol(self.operator)
        value_str = self.get_value_display()
        return f"{self.attribute} {op_symbol} {value_str}"

    def matches_value(self, value: str) -> bool:
        """
        Check if a given value would select this branch.

        Useful for Phase 2 when determining which branch to take.
        """
        if self.operator == "equals":
            if isinstance(self.value, list):
                return value in self.value
            return value == self.value
        elif self.operator == "not_equals":
            if isinstance(self.value, list):
                return value not in self.value
            return value != self.value
        elif self.operator == "in":
            if isinstance(self.value, list):
                return value in self.value
            return value == self.value
        elif self.operator == "not_in":
            if isinstance(self.value, list):
                return value not in self.value
            return value != self.value
        return False


# Rebuild model for self-referential type
BranchCondition.model_rebuild()


class IncomingEdge(BaseModel):
    """
    Represents an incoming edge from a parent node in a DAG structure.

    When multiple paths lead to the same world state, we merge nodes
    and track each incoming edge separately with its own transition metadata.
    """

    parent_id: str
    action_name: str
    action_parameters: Dict[str, str] = Field(default_factory=dict)
    action_status: str = "ok"
    action_error: Optional[str] = None
    branch_condition: Optional[BranchCondition] = None
    changes: List[Dict[str, Any]] = Field(default_factory=list)


class TreeNode(BaseModel):
    """
    A node in the simulation DAG.

    Each node represents a world state and the action(s) that led to it.
    The root node has no parents and no action (it's the initial state).

    DAG Support:
    - Multiple parent nodes can lead to the same world state
    - Each incoming edge tracks its own transition metadata (changes, branch condition)
    - The primary edge's metadata is stored in action_name, action_status, etc.
    - Additional edges are stored in incoming_edges list
    """

    id: str  # Sequential ID: state0, state1, etc.
    snapshot: WorldSnapshot

    # DAG support: multiple parents possible
    parent_ids: List[str] = Field(default_factory=list)
    children_ids: List[str] = Field(default_factory=list)

    # Incoming edges from multiple parents (for DAG merging)
    # Each edge tracks: parent_id, action_name, action_status, changes, branch_condition
    incoming_edges: List[IncomingEdge] = Field(default_factory=list)

    # Action information for the PRIMARY edge (first parent) - None for root node
    action_name: Optional[str] = None
    action_parameters: Dict[str, str] = Field(default_factory=dict)
    action_status: str = "ok"  # ok, rejected, constraint_violated, error
    action_error: Optional[str] = None

    # Branch information - what condition led to this node (for primary edge)
    branch_condition: Optional[BranchCondition] = None

    # Changes applied in this transition (for primary edge)
    changes: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def is_root(self) -> bool:
        """Check if this is the root node (initial state)."""
        return len(self.parent_ids) == 0

    @property
    def parent_id(self) -> Optional[str]:
        """Get the primary parent ID (first parent for backward compatibility)."""
        return self.parent_ids[0] if self.parent_ids else None

    @property
    def has_multiple_parents(self) -> bool:
        """Check if this node has multiple incoming edges (merged node)."""
        return len(self.parent_ids) > 1

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf node (no children yet)."""
        return len(self.children_ids) == 0

    @property
    def succeeded(self) -> bool:
        """Check if the action at this node succeeded."""
        return self.action_status == "ok"

    @property
    def failed(self) -> bool:
        """Check if the action at this node failed."""
        return self.action_status in ("rejected", "constraint_violated", "error")

    @property
    def change_count(self) -> int:
        """Number of changes in this transition."""
        return len(self.changes)

    def describe(self) -> str:
        """Human-readable description of this node."""
        if self.is_root:
            return f"[{self.id}] Initial State"

        action_desc = self.action_name or "unknown"
        if self.action_status != "ok":
            action_desc += f" ({self.action_status})"

        if self.branch_condition:
            return f"[{self.id}] {action_desc} | {self.branch_condition.describe()}"
        return f"[{self.id}] {action_desc}"

    def get_changed_attributes(self) -> List[str]:
        """Get list of attribute paths that changed in this transition."""
        return [c["attribute"] for c in self.changes if "attribute" in c]


class SimulationTree(BaseModel):
    """
    Tree structure for simulation execution.

    The tree tracks:
    - All nodes (world states) created during simulation
    - The relationships between nodes (parent-child)
    - The current execution path (for Phase 1 linear execution)
    - Statistics about the simulation

    Phase 1: Linear execution with current_path tracking single path
    Phase 2: Full tree with multiple paths (branches)
    """

    simulation_id: str
    object_type: str
    object_name: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # CLI command that generated this simulation (for display in visualization)
    cli_command: Optional[str] = None

    # Actions that were executed (for reference)
    actions: List[str] = Field(default_factory=list)

    # Action definitions for visualization (preconditions/postconditions)
    action_definitions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Tree structure
    root_id: Optional[str] = None
    nodes: Dict[str, TreeNode] = Field(default_factory=dict)

    # Internal counter for generating node IDs (excluded from serialization)
    _node_counter: int = 0

    # Phase 1: Linear execution tracking
    current_path: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    # =========================================================================
    # Node Access
    # =========================================================================

    @property
    def root(self) -> Optional[TreeNode]:
        """Get the root node."""
        if self.root_id is None:
            return None
        return self.nodes.get(self.root_id)

    def get_node(self, node_id: str) -> Optional[TreeNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_current_node(self) -> Optional[TreeNode]:
        """Get the current node (last in path for Phase 1)."""
        if not self.current_path:
            return None
        return self.nodes.get(self.current_path[-1])

    # =========================================================================
    # Node Management
    # =========================================================================

    def generate_node_id(self) -> str:
        """Generate a sequential node ID (state0, state1, etc.)."""
        node_id = f"state{self._node_counter}"
        self._node_counter += 1
        return node_id

    def add_node(self, node: TreeNode) -> None:
        """
        Add a node to the DAG.

        Automatically handles:
        - Setting root_id for root nodes
        - Updating parent's children list (all parents for DAG)
        - Tracking current path (Phase 1)
        """
        self.nodes[node.id] = node

        if node.is_root:
            self.root_id = node.id
            self.current_path = [node.id]
        else:
            # Update all parents' children lists (DAG support)
            for pid in node.parent_ids:
                if pid in self.nodes:
                    parent = self.nodes[pid]
                    if node.id not in parent.children_ids:
                        parent.children_ids.append(node.id)

            # Add to current path (Phase 1: linear)
            self.current_path.append(node.id)

    def add_branch_nodes(self, parent_id: str, nodes: List[TreeNode]) -> None:
        """
        Add multiple branch nodes from a single parent.

        This is for Phase 2 branching support. In Phase 1, this should
        only be called with a single node.
        """
        for node in nodes:
            # Set parent_ids if not already set
            if parent_id not in node.parent_ids:
                node.parent_ids.append(parent_id)
            self.nodes[node.id] = node

            if parent_id in self.nodes:
                parent = self.nodes[parent_id]
                if node.id not in parent.children_ids:
                    parent.children_ids.append(node.id)

        # Phase 1: Only add first node to current path
        if nodes:
            self.current_path.append(nodes[0].id)

    def add_edge_to_existing_node(self, existing_node_id: str, parent_id: str, edge: IncomingEdge) -> None:
        """
        Add an additional incoming edge to an existing node (DAG merging).

        This is called when a new branch would create a duplicate node.
        Instead of creating a new node, we add an edge from the new parent
        to the existing node.

        Args:
            existing_node_id: ID of the existing node to merge into
            parent_id: ID of the new parent node
            edge: The incoming edge with transition metadata
        """
        node = self.nodes.get(existing_node_id)
        if not node:
            return

        # Add parent if not already present
        if parent_id not in node.parent_ids:
            node.parent_ids.append(parent_id)

        # Add the incoming edge
        node.incoming_edges.append(edge)

        # Update parent's children list
        if parent_id in self.nodes:
            parent = self.nodes[parent_id]
            if existing_node_id not in parent.children_ids:
                parent.children_ids.append(existing_node_id)

    # =========================================================================
    # Tree Traversal
    # =========================================================================

    def get_leaf_nodes(self) -> List[TreeNode]:
        """Get all leaf nodes (nodes with no children)."""
        return [node for node in self.nodes.values() if node.is_leaf]

    def get_path_to_node(self, node_id: str) -> List[TreeNode]:
        """Get the path from root to a specific node."""
        path: List[TreeNode] = []
        current_id: Optional[str] = node_id

        while current_id is not None:
            node = self.nodes.get(current_id)
            if node is None:
                break
            path.insert(0, node)
            current_id = node.parent_id

        return path

    def get_children(self, node_id: str) -> List[TreeNode]:
        """Get all direct children of a node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]

    def get_siblings(self, node_id: str) -> List[TreeNode]:
        """Get all siblings of a node (same parent, excluding self)."""
        node = self.nodes.get(node_id)
        if not node or not node.parent_id:
            return []

        parent = self.nodes.get(node.parent_id)
        if not parent:
            return []

        return [self.nodes[cid] for cid in parent.children_ids if cid in self.nodes and cid != node_id]

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_depth(self) -> int:
        """Get the maximum depth of the tree."""
        if not self.nodes:
            return 0
        return max(len(self.get_path_to_node(node_id)) for node_id in self.nodes)

    def get_width(self) -> int:
        """Get the maximum width (number of nodes at any level)."""
        if not self.nodes:
            return 0

        level_counts: Dict[int, int] = {}
        for node_id in self.nodes:
            level = len(self.get_path_to_node(node_id)) - 1
            level_counts[level] = level_counts.get(level, 0) + 1

        return max(level_counts.values()) if level_counts else 0

    def count_success_nodes(self) -> int:
        """Count nodes where action succeeded."""
        return sum(1 for n in self.nodes.values() if n.succeeded and not n.is_root)

    def count_failed_nodes(self) -> int:
        """Count nodes where action failed."""
        return sum(1 for n in self.nodes.values() if n.failed)

    def count_branches(self) -> int:
        """Count total number of branch points (nodes with multiple children)."""
        return sum(1 for n in self.nodes.values() if len(n.children_ids) > 1)

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the tree."""
        return {
            "total_nodes": len(self.nodes),
            "depth": self.get_depth(),
            "width": self.get_width(),
            "leaf_nodes": len(self.get_leaf_nodes()),
            "branch_points": self.count_branches(),
            "successful_actions": self.count_success_nodes(),
            "failed_actions": self.count_failed_nodes(),
            "path_length": len(self.current_path),
        }

    # =========================================================================
    # Description and Serialization
    # =========================================================================

    def describe_path(self) -> str:
        """Describe the current execution path."""
        return " -> ".join(self.current_path)

    def to_dict(self) -> Dict[str, Any]:
        """Convert tree to dictionary for YAML serialization."""
        # Custom serialization to handle DAG structure
        nodes_dict = {}
        for node_id, node in self.nodes.items():
            node_data = node.model_dump()
            # Ensure incoming_edges is included
            if node.incoming_edges:
                node_data["incoming_edges"] = [e.model_dump() for e in node.incoming_edges]
            nodes_dict[node_id] = node_data

        result = {
            "simulation_id": self.simulation_id,
            "object_type": self.object_type,
            "object_name": self.object_name,
            "created_at": self.created_at,
            "cli_command": self.cli_command,
            "actions": self.actions,
            "root_id": self.root_id,
            "current_path": self.current_path,
            "nodes": nodes_dict,
        }

        # Include action definitions if present
        if self.action_definitions:
            result["action_definitions"] = self.action_definitions

        return result

    def count_merged_nodes(self) -> int:
        """Count nodes with multiple parents (merged nodes)."""
        return sum(1 for n in self.nodes.values() if n.has_multiple_parents)

    def count_edges(self) -> int:
        """Count total number of edges in the DAG."""
        return sum(len(n.parent_ids) for n in self.nodes.values())


__all__ = [
    "BranchCondition",
    "IncomingEdge",
    "NodeStatus",
    "SimulationTree",
    "TreeNode",
    "WorldSnapshot",
]
