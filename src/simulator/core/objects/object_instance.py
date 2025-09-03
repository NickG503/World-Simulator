from __future__ import annotations
from typing import Any, Dict
from pydantic import BaseModel, Field
from .object_type import ObjectType
from .part import PartInstance
from simulator.core.attributes import AttributeInstance, AttributeSpec


class ObjectInstance(BaseModel):
    """Runtime instance of an object."""

    type: ObjectType
    parts: Dict[str, PartInstance]
    global_attributes: Dict[str, AttributeInstance]
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def deep_copy(self) -> "ObjectInstance":
        # Pydantic's model_copy(deep=True) for deep clone
        return self.model_copy(deep=True)

