from __future__ import annotations

"""Schema definitions for qualitative space YAML files."""

from typing import List

from pydantic import BaseModel, Field

from simulator.core.attributes.qualitative_space import QualitativeSpace


class QualitativeSpaceEntrySpec(BaseModel):
    id: str
    name: str
    levels: List[str] = Field(default_factory=list)

    def build(self) -> QualitativeSpace:
        return QualitativeSpace(id=self.id, name=self.name, levels=self.levels)


class QualitativeSpaceFileSpec(BaseModel):
    spaces: List[QualitativeSpaceEntrySpec] = Field(default_factory=list)


__all__ = ["QualitativeSpaceFileSpec", "QualitativeSpaceEntrySpec"]

