from __future__ import annotations

"""Schema definitions for action YAML files."""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from simulator.core.actions.parameter import ParameterSpec
from simulator.core.actions.specs import (
    ConditionSpec,
    EffectSpec,
    build_condition,
    build_effect,
    parse_condition_spec,
    parse_effect_spec,
)


class ParameterDefinitionSpec(BaseModel):
    """Declarative description of a single action parameter."""

    type: str = "choice"
    choices: Optional[List[str]] = None
    required: bool = True

    def to_runtime(self, name: str) -> ParameterSpec:
        return ParameterSpec(name=name, type=self.type, choices=self.choices, required=self.required)


class ActionFileSpec(BaseModel):
    """Top-level schema for an action YAML document."""

    action: str
    object_type: str
    description: Optional[str] = None
    parameters: Dict[str, ParameterDefinitionSpec] = Field(default_factory=dict)
    preconditions: List[ConditionSpec] = Field(default_factory=list)
    effects: List[EffectSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    @field_validator("parameters", mode="before")
    @classmethod
    def _normalize_parameters(cls, value):
        if value is None:
            return {}
        return value

    @field_validator("preconditions", mode="before")
    @classmethod
    def _parse_preconditions(cls, value):
        if value is None:
            return []
        return [parse_condition_spec(item) for item in value]

    @field_validator("effects", mode="before")
    @classmethod
    def _parse_effects(cls, value):
        if value is None:
            return []
        return [parse_effect_spec(item) for item in value]

    def build_parameters(self) -> Dict[str, ParameterSpec]:
        return {name: spec.to_runtime(name) for name, spec in self.parameters.items()}

    def build_preconditions(self):
        return [build_condition(cond) for cond in self.preconditions]

    def build_effects(self):
        return [build_effect(effect) for effect in self.effects]


__all__ = ["ActionFileSpec", "ParameterDefinitionSpec"]
