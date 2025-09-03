from __future__ import annotations
from typing import Dict, List, Any
from pydantic import BaseModel, Field
from .part import PartSpec
from simulator.core.attributes import AttributeSpec


class ObjectConstraint(BaseModel):
    """Raw constraint data from YAML - converted to Constraint instances at runtime.

    'condition' and 'requires' may be structured condition dicts.
    """
    type: str
    condition: Any = None
    requires: Any = None
    
    # Allow additional fields for different constraint types
    model_config = {"extra": "allow"}


class ObjectType(BaseModel):
    """Schema for an object with parts hierarchy."""

    name: str
    parts: Dict[str, PartSpec]
    global_attributes: Dict[str, AttributeSpec] = Field(default_factory=dict)
    constraints: List[ObjectConstraint] = Field(default_factory=list)
