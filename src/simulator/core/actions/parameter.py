from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, field_validator


class ParameterSpec(BaseModel):
    name: str
    type: str = "choice"  # extendable
    choices: Optional[List[str]] = None
    required: bool = True

    @field_validator("name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("parameter name cannot be empty")
        return v


class ParameterReference(BaseModel):
    type: str = "parameter_ref"
    name: str
