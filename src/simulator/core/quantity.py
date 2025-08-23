from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import List


class QuantitySpace(BaseModel):
    """An ordered qualitative value space (e.g., [empty, low, med, high])."""
    name: str
    levels: List[str]

    @field_validator("levels")
    @classmethod
    def _non_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("QuantitySpace.levels cannot be empty")
        if len(set(v)) != len(v):
            raise ValueError("QuantitySpace.levels must be unique")
        return v

    def has(self, value: str) -> bool:
        return value in self.levels

    def clamp(self, value: str) -> str:
        if value not in self.levels:
            # If not present, clamp to nearest: here we default to first
            return self.levels[0]
        return value

    def step(self, value: str, direction: str) -> str:
        """Move one step up/down if possible; otherwise stay in place."""
        try:
            idx = self.levels.index(value)
        except ValueError:
            # If unknown value, clamp to first
            idx = 0
        if direction == "up":
            idx = min(idx + 1, len(self.levels) - 1)
        elif direction == "down":
            idx = max(idx - 1, 0)
        elif direction == "none":
            pass
        else:
            raise ValueError(f"Unknown direction: {direction!r}")
        return self.levels[idx]