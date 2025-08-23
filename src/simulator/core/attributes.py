from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional
from simulator.core.quantity import QuantitySpace


class AttributeType(BaseModel):
    name: str
    space: QuantitySpace
    mutable: bool = True
    default: Optional[str] = None

    @field_validator("default")
    @classmethod
    def _default_in_space(cls, v: Optional[str], info):
        if v is None:
            return v
        space = info.data.get("space")
        if space and not space.has(v):
            raise ValueError(f"default {v!r} not in quantity space {space.levels!r}")
        return v