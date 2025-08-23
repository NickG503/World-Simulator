from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Dict
from simulator.core.attributes import AttributeType
from simulator.core.state import ObjectState


class ObjectType(BaseModel):
    name: str
    version: int
    attributes: Dict[str, AttributeType]

    @field_validator("attributes")
    @classmethod
    def _non_empty(cls, v: Dict[str, AttributeType]) -> Dict[str, AttributeType]:
        if not v:
            raise ValueError("ObjectType.attributes cannot be empty")
        return v

    def default_state(self) -> ObjectState:
        values = {}
        for attr_name, attr in self.attributes.items():
            if attr.default is None:
                # If no default, choose first in space
                values[attr_name] = attr.space.levels[0]
            else:
                values[attr_name] = attr.default
        return ObjectState(object_type=self, values=values)