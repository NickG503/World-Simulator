from __future__ import annotations

"""Schema definitions for constraint YAML entries."""

from typing import Any, Dict, Literal, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator

from simulator.core.actions.specs import ConditionSpec, parse_condition_spec


class ConstraintSpec(BaseModel):
    """Base spec for an object-level constraint."""

    type: str

    model_config = ConfigDict(extra="allow")


class DependencyConstraintSpec(ConstraintSpec):
    type: Literal["dependency"]
    condition: ConditionSpec
    requires: ConditionSpec

    @field_validator("condition", "requires", mode="before")
    @classmethod
    def _parse_condition(cls, value: Any) -> ConditionSpec:
        return parse_condition_spec(value)


_SPEC_MAP: Dict[str, Type[ConstraintSpec]] = {
    "dependency": DependencyConstraintSpec,
}


def parse_constraint_spec(data: Any) -> ConstraintSpec:
    if isinstance(data, ConstraintSpec):
        return data
    if not isinstance(data, dict):
        raise TypeError("Constraint entry must be a mapping")
    ctype = data.get("type")
    cls = _SPEC_MAP.get(ctype)
    if cls is None:
        raise ValueError(f"Unknown constraint type: {ctype}")
    return cls.model_validate(data)


__all__ = [
    "ConstraintSpec",
    "DependencyConstraintSpec",
    "parse_constraint_spec",
]

