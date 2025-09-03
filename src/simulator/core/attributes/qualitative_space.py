from __future__ import annotations
from typing import List, Literal
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

