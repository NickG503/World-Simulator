from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class AttributeSpec(BaseModel):
    """Specification for an attribute that can be attached to any part."""

    name: str
    space_id: str  # References a QualitativeSpace
    mutable: bool = True
    default_value: Optional[str] = None

    @field_validator("name", "space_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("field must be non-empty")
        return v
