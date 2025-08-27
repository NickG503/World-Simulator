"""
Qualitative Value Spaces

This module defines QuantitySpace, which represents ordered qualitative values
like [empty, low, medium, high] instead of numeric ranges. This is fundamental
to qualitative reasoning about everyday objects.

Key concepts:
- Values are discrete and ordered (e.g., "low" comes before "high")
- Stepping moves between adjacent values in the ordering
- All operations preserve the discrete nature of the space
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import List, Literal


class QuantitySpace(BaseModel):
    """
    An ordered qualitative value space for discrete reasoning.
    
    QuantitySpace represents a finite, ordered set of qualitative values
    that can be used for reasoning about object attributes without
    requiring precise numeric measurements.
    
    Examples:
        Battery level: [empty, low, medium, high]
        Temperature: [cold, warm, hot, boiling]
        Size: [tiny, small, medium, large, huge]
    
    Attributes:
        name: Human-readable identifier for this space
        levels: Ordered list of qualitative values (first = lowest)
    """
    name: str
    levels: List[str]

    @field_validator("levels")
    @classmethod
    def _validate_levels(cls, v: List[str]) -> List[str]:
        """Ensure levels list is non-empty and contains unique values."""
        if not v:
            raise ValueError("QuantitySpace.levels cannot be empty")
        if len(set(v)) != len(v):
            raise ValueError("QuantitySpace.levels must be unique")
        return v

    def has(self, value: str) -> bool:
        """
        Check if a value exists in this quantity space.
        
        Args:
            value: The value to check
            
        Returns:
            True if value is a valid level in this space
        """
        return value in self.levels

    def clamp(self, value: str) -> str:
        """
        Clamp an invalid value to the first (lowest) level.
        
        Used as a fallback when a value is outside the valid range.
        
        Args:
            value: The value to clamp
            
        Returns:
            The original value if valid, otherwise the first level
        """
        if value not in self.levels:
            return self.levels[0]
        return value

    def step(self, value: str, direction: Literal["up", "down", "none"]) -> str:
        """
        Move one step in the specified direction within the quantity space.
        
        This is the core operation for qualitative reasoning - moving between
        adjacent levels while respecting boundaries.
        
        Args:
            value: Current value (must be in this space)
            direction: Direction to step ("up", "down", or "none")
            
        Returns:
            New value after stepping, or original value if at boundary
            
        Raises:
            ValueError: If direction is invalid
            
        Examples:
            >>> space = QuantitySpace(name="battery", levels=["empty", "low", "med", "high"])
            >>> space.step("low", "up")
            "med"
            >>> space.step("empty", "down")  # At boundary
            "empty"
        """
        # Find current position, defaulting to first level if not found
        try:
            idx = self.levels.index(value)
        except ValueError:
            idx = 0
            
        # Apply step operation with boundary checking
        if direction == "up":
            idx = min(idx + 1, len(self.levels) - 1)
        elif direction == "down":
            idx = max(idx - 1, 0)
        elif direction == "none":
            # No change - used for conditional effects
            pass
        else:
            raise ValueError(f"Unknown direction: {direction!r}. Must be 'up', 'down', or 'none'")
            
        return self.levels[idx]

    def get_index(self, value: str) -> int:
        """
        Get the numeric index of a value in the levels list.
        
        Args:
            value: The value to find
            
        Returns:
            Index of the value (0-based)
            
        Raises:
            ValueError: If value is not in this space
        """
        return self.levels.index(value)

    def __str__(self) -> str:
        """String representation showing the ordered levels."""
        return f"QuantitySpace({self.name}: {' → '.join(self.levels)})"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return f"QuantitySpace(name='{self.name}', levels={self.levels})"