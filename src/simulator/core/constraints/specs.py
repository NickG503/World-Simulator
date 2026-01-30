from __future__ import annotations

"""Schema definitions for constraint YAML entries."""

from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, field_validator

from simulator.core.actions.specs import (
    ConditionSpec,
    EffectSpec,
    parse_condition_spec,
    parse_effect_spec,
)


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


class BranchingConstraintSpec(ConstraintSpec):
    """Spec for a branching constraint that creates atomic state branches."""

    type: Literal["branching_constraint"]
    name: Optional[str] = None  # Optional name for visualization
    condition: ConditionSpec  # IF condition
    effects: List[EffectSpec]  # Effects when condition is true (IF branch)
    else_effects: List[EffectSpec] = []  # Effects when condition is false (ELSE branch)

    @field_validator("condition", mode="before")
    @classmethod
    def _parse_condition(cls, value: Any) -> ConditionSpec:
        return parse_condition_spec(value)

    @field_validator("effects", "else_effects", mode="before")
    @classmethod
    def _parse_effects(cls, value: Any) -> List[EffectSpec]:
        if value is None:
            return []
        if isinstance(value, list):
            return [parse_effect_spec(item) for item in value]
        return [parse_effect_spec(value)]


_SPEC_MAP: Dict[str, Type[ConstraintSpec]] = {
    "dependency": DependencyConstraintSpec,
    "branching_constraint": BranchingConstraintSpec,
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
    "BranchingConstraintSpec",
    "parse_constraint_spec",
]
