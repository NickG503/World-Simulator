from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator


class QualitativeSpace(BaseModel):
    """Reusable ordered qualitative value space."""

    id: str  # e.g., "binary_state", "battery_level"
    name: str
    levels: List[str]

    @field_validator("id", "name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("id/name must be non-empty")
        return v

    @field_validator("levels")
    @classmethod
    def _levels_valid(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("levels cannot be empty")
        if len(set(v)) != len(v):
            raise ValueError("levels must be unique")
        return v

    def has(self, value: str) -> bool:
        return value in self.levels

    def next_level(self, current: str, direction: Literal["up", "down", "none"]) -> str:
        """Get next level in specified direction."""
        try:
            idx = self.levels.index(current)
        except ValueError:
            idx = 0
        if direction == "up":
            idx = min(idx + 1, len(self.levels) - 1)
        elif direction == "down":
            idx = max(idx - 1, 0)
        elif direction == "none":
            pass
        else:
            raise ValueError(f"Invalid direction: {direction}")
        return self.levels[idx]

    def constrained_levels(
        self,
        *,
        last_known_value: Optional[str],
        trend: Optional[Literal["up", "down", "none"]],
    ) -> List[str]:
        """Return ordered levels consistent with a known trend direction.

        Includes the last_known_value and all values in the trend direction.
        E.g., if battery was "high" and trending down, options are ["empty", "low", "medium", "high"].
        """
        if trend not in ("up", "down") or not last_known_value or last_known_value not in self.levels:
            return list(self.levels)
        idx = self.levels.index(last_known_value)
        if trend == "down":
            # Include last_known_value and all levels below it
            allowed = self.levels[: idx + 1]
        else:  # trend == "up"
            # Include last_known_value and all levels above it
            allowed = self.levels[idx:]
        return list(allowed) if allowed else list(self.levels)

    def get_values_for_comparison(self, value: str, operator: str) -> List[str]:
        """Return all values from the space that satisfy a comparison operator.

        For ordered qualitative spaces, this expands comparison operators to value sets:
        - gte (>=): all values from `value` to the end (inclusive)
        - gt (>): all values after `value` (exclusive)
        - lte (<=): all values from start to `value` (inclusive)
        - lt (<): all values before `value` (exclusive)

        Args:
            value: The reference value to compare against
            operator: One of "gt", "gte", "lt", "lte"

        Returns:
            List of values that satisfy the comparison

        Raises:
            ValueError: If value is not in the space or operator is invalid
        """
        if value not in self.levels:
            raise ValueError(f"Value '{value}' not in space '{self.id}' levels {self.levels}")

        idx = self.levels.index(value)

        if operator == "gte":
            return list(self.levels[idx:])
        elif operator == "gt":
            return list(self.levels[idx + 1 :])
        elif operator == "lte":
            return list(self.levels[: idx + 1])
        elif operator == "lt":
            return list(self.levels[:idx])
        else:
            raise ValueError(f"Invalid comparison operator: {operator}")
