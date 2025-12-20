"""
Simulation data models and snapshot utilities.

Models used by TreeSimulationRunner:
- AttributeSnapshot: State of a single attribute
- PartStateSnapshot: State of an object part
- ObjectStateSnapshot: Complete object state
- ActionRequest: Action specification
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field


class AttributeSnapshot(BaseModel):
    """
    Snapshot of an attribute's state.

    In Phase 2, the value can be either:
    - A single string value (known state)
    - A list of strings (set of possible values from branching/trends)
    - None (uninitialized)
    """

    value: Union[str, List[str], None] = None  # Single value OR set of possible values
    trend: Optional[str] = None
    last_known_value: Optional[str] = None
    last_trend_direction: Optional[str] = None
    space_id: Optional[str] = None

    def is_value_set(self) -> bool:
        """Check if the value is a set of possible values (list)."""
        return isinstance(self.value, list)

    def get_value_as_set(self) -> Set[str]:
        """
        Get the value as a set.

        Returns:
            Set of possible values. For single values, returns a set with one element.
            For value sets, returns the set of all values.
            For None, returns empty set.
        """
        if isinstance(self.value, list):
            return set(self.value)
        return {self.value} if self.value else set()

    def get_single_value(self) -> Optional[str]:
        """
        Get the value as a single string.

        Returns:
            The single value, or the first value if a set, or None.
        """
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def is_unknown(self) -> bool:
        """
        Check if the attribute value is unknown.

        In Phase 2, a value is "unknown" if:
        - It's None
        - It's the string "unknown"
        - It's a set with more than one value (uncertain state)
        """
        if self.value is None:
            return True
        if isinstance(self.value, list):
            return len(self.value) != 1
        return self.value == "unknown"


class PartStateSnapshot(BaseModel):
    attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ObjectStateSnapshot(BaseModel):
    type: str
    parts: Dict[str, PartStateSnapshot] = Field(default_factory=dict)
    global_attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    name: str
    parameters: Dict[str, str] = Field(default_factory=dict)
