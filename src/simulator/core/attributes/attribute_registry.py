from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field

from .attribute_spec import AttributeSpec
from .qualitative_space import QualitativeSpace


class QualitativeSpaceRegistry(BaseModel):
    spaces: Dict[str, QualitativeSpace] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def register(self, space: QualitativeSpace) -> None:
        if space.id in self.spaces:
            raise ValueError(f"Duplicate qualitative space id: {space.id}")
        self.spaces[space.id] = space

    def get(self, space_id: str) -> QualitativeSpace:
        if space_id not in self.spaces:
            available = ", ".join(sorted(self.spaces.keys()))
            raise KeyError(f"Unknown space id: {space_id}. Available: {available}")
        return self.spaces[space_id]


class AttributeRegistry(BaseModel):
    attributes: Dict[str, AttributeSpec] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def register(self, spec: AttributeSpec) -> None:
        if spec.name in self.attributes:
            raise ValueError(f"Duplicate attribute spec name: {spec.name}")
        self.attributes[spec.name] = spec

    def get(self, name: str) -> AttributeSpec:
        if name not in self.attributes:
            available = ", ".join(sorted(self.attributes.keys()))
            raise KeyError(f"Unknown attribute spec: {name}. Available: {available}")
        return self.attributes[name]
