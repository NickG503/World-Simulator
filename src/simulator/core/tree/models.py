"""
Tree-based simulation data models.

These models represent the tree structure for simulation execution:
- WorldSnapshot: Immutable state of the world at a point in time
- BranchCondition: Describes what condition led to a specific branch
- TreeNode: A node in the simulation tree (represents a world state)
- SimulationTree: The complete tree structure with all nodes

Architecture for Future Branching:
----------------------------------
Phase 1 (Current): Linear execution
    - All values known
    - Single path through tree
    - Each action produces exactly one child node

Phase 2 (Future): Branching on unknowns
    - Precondition branches: When precondition attribute is unknown
        → Creates 2 branches: success (attribute satisfies condition) / fail
    - Postcondition branches: When postcondition attribute is unknown
        → Creates N+1 branches: one for each if/elif case + one for else
    - Max branches per action = 2 × (postcondition_cases + 1)

Tree Structure:
    state0 (Initial)
    └── state1 (turn_on succeeded)
        ├── state2a (battery.level == high → brightness = high)
        ├── state2b (battery.level == medium → brightness = medium)
        └── state2c (battery.level in {low, empty} → brightness = low)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from simulator.core.simulation_runner import ObjectStateSnapshot


class BranchSource(str, Enum):
    """Source of a branch condition."""

    PRECONDITION = "precondition"
    POSTCONDITION = "postcondition"


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


class BranchCondition(BaseModel):
    """
    Describes the condition that led to this branch.

    This captures what decision was made to reach this node:
    - For precondition branches: whether the precondition passed or failed
    - For postcondition branches: which if/elif/else case was matched

    In Phase 2, the value can be a single value or a set of values (for else branches).
    """

    attribute: str  # e.g., "battery.level"
    operator: str  # e.g., "equals", "not_equals", "in"
    value: Union[str, List[str]]  # Single value OR set of values (for else branch)
    source: Literal["precondition", "postcondition"]

    # For postcondition branches with if/elif/else
    branch_type: Literal["if", "elif", "else", "success", "fail"] = "if"

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        """Validate operator is supported."""
        valid_ops = {"equals", "not_equals", "lt", "lte", "gt", "gte", "in", "not_in"}
        # Also accept display forms
        if v in valid_ops or v.startswith("not "):
            return v
        return v

    def is_value_set(self) -> bool:
        """Check if the value is a set of possible values."""
        return isinstance(self.value, list)

    def get_value_display(self) -> str:
        """Get a display string for the value (handles sets)."""
        if isinstance(self.value, list):
            return "{" + ", ".join(self.value) + "}"
        return str(self.value)

    def describe(self) -> str:
        """Human-readable description of the branch condition."""
        op_map = {
            "equals": "==",
            "not_equals": "!=",
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
            "in": "in",
            "not_in": "not in",
        }
        op_symbol = op_map.get(self.operator, self.operator)
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


class TreeNode(BaseModel):
    """
    A node in the simulation tree.

    Each node represents a world state and the action that led to it.
    The root node has no parent and no action (it's the initial state).
    """

    id: str  # Sequential ID: state0, state1, etc.
    snapshot: WorldSnapshot
    parent_id: Optional[str] = None
    children_ids: List[str] = Field(default_factory=list)

    # Action information (None for root node)
    action_name: Optional[str] = None
    action_parameters: Dict[str, str] = Field(default_factory=dict)
    action_status: str = "ok"  # ok, rejected, constraint_violated, error
    action_error: Optional[str] = None

    # Branch information - what condition led to this node
    branch_condition: Optional[BranchCondition] = None

    # Changes applied in this transition
    changes: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def is_root(self) -> bool:
        """Check if this is the root node (initial state)."""
        return self.parent_id is None

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
        Add a node to the tree.

        Automatically handles:
        - Setting root_id for root nodes
        - Updating parent's children list
        - Tracking current path (Phase 1)
        """
        self.nodes[node.id] = node

        if node.is_root:
            self.root_id = node.id
            self.current_path = [node.id]
        else:
            # Update parent's children list
            if node.parent_id and node.parent_id in self.nodes:
                parent = self.nodes[node.parent_id]
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
            node.parent_id = parent_id
            self.nodes[node.id] = node

            if parent_id in self.nodes:
                parent = self.nodes[parent_id]
                if node.id not in parent.children_ids:
                    parent.children_ids.append(node.id)

        # Phase 1: Only add first node to current path
        if nodes:
            self.current_path.append(nodes[0].id)

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
        return {
            "simulation_id": self.simulation_id,
            "object_type": self.object_type,
            "object_name": self.object_name,
            "created_at": self.created_at,
            "cli_command": self.cli_command,
            "actions": self.actions,
            "root_id": self.root_id,
            "current_path": self.current_path,
            "nodes": {node_id: node.model_dump() for node_id, node in self.nodes.items()},
        }


__all__ = [
    "BranchCondition",
    "BranchSource",
    "NodeStatus",
    "SimulationTree",
    "TreeNode",
    "WorldSnapshot",
]
