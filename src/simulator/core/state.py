from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Dict, Literal
from simulator.core.attributes import AttributeType


Trend = Literal["up", "down", "none"]


class ObjectState(BaseModel):
    object_type: "ObjectType"  # Use string annotation
    values: Dict[str, str]
    trends: Dict[str, Trend] = {}
    
    model_config = {"arbitrary_types_allowed": True}

    @field_validator("values")
    @classmethod
    def _validate_values(cls, v: Dict[str, str], info):
        obj_type: ObjectType = info.data.get("object_type")
        if obj_type is None:
            return v
        # Ensure all attributes present and valid
        for attr_name, attr in obj_type.attributes.items():
            if attr_name not in v:
                raise ValueError(f"Missing value for attribute '{attr_name}'")
            if not attr.space.has(v[attr_name]):
                raise ValueError(
                    f"Attribute '{attr_name}' has invalid value {v[attr_name]!r}; "
                    f"must be one of {attr.space.levels!r}"
                )
        # Forbid unknown attributes
        for k in v.keys():
            if k not in obj_type.attributes:
                raise ValueError(f"Unknown attribute '{k}' for type '{obj_type.name}'")
        return v

    def set_value(self, attr_name: str, new_value: str) -> None:
        attr: AttributeType = self.object_type.attributes[attr_name]
        if not attr.mutable:
            raise ValueError(f"Attribute '{attr_name}' is immutable")
        if not attr.space.has(new_value):
            raise ValueError(f"Value {new_value!r} not in space {attr.space.levels!r}")
        self.values[attr_name] = new_value