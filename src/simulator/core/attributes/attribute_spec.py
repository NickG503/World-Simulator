from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, field_validator, Field


class AttributeConstraint(BaseModel):
    """Placeholder for attribute-level constraints (future use)."""

    type: str
    # Additional fields depending on constraint type


class AttributeSpec(BaseModel):
    """Specification for an attribute that can be attached to any part."""

    name: str
    space_id: str  # References a QualitativeSpace
    mutable: bool = True
    default_value: Optional[str] = None
    constraints: List[AttributeConstraint] = Field(default_factory=list)

    @field_validator("name", "space_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("field must be non-empty")
        return v
