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
        """Return ordered levels consistent with a known trend direction."""
        if trend not in ("up", "down") or not last_known_value or last_known_value not in self.levels:
            return list(self.levels)
        idx = self.levels.index(last_known_value)
        if trend == "down":
            allowed = self.levels[:idx + 1]
        else:  # trend == "up"
            allowed = self.levels[idx :]
        return list(allowed) if allowed else list(self.levels)
