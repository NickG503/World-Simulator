"""Schema definitions for solver rule YAML entries.

Solver rules define implication relationships:
- If condition is true, apply 'implies' effects
- If condition is false, apply 'otherwise' effects
- Cases provide if/elif/else branching within a rule
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from simulator.core.actions.specs import (
    ConditionSpec,
    EffectSpec,
    parse_condition_spec,
    parse_effect_spec,
)


class SolverCaseSpec(BaseModel):
    """A case within a solver rule (for if/elif/else branching)."""

    condition: ConditionSpec
    implies: List[EffectSpec]

    model_config = ConfigDict(extra="forbid")

    @field_validator("condition", mode="before")
    @classmethod
    def _parse_condition(cls, value: Any) -> ConditionSpec:
        return parse_condition_spec(value)

    @field_validator("implies", mode="before")
    @classmethod
    def _parse_implies(cls, value: Any) -> List[EffectSpec]:
        if value is None:
            return []
        if isinstance(value, list):
            return [parse_effect_spec(item) for item in value]
        return [parse_effect_spec(value)]


class SolverRuleSpec(BaseModel):
    """Spec for a solver rule that derives state from conditions.

    A solver rule can have one of two forms:
    1. Simple: condition -> implies / otherwise
    2. Cases: precondition gate + multiple cases with if/elif/else

    Attributes:
        name: Unique identifier for the rule
        priority: Lower priority rules run first (default: 100)
        description: Human-readable description
        precondition: Gate condition - rule only applies if this is true
        condition: Main condition for simple form
        implies: Effects when condition is true (simple form)
        otherwise: Effects when condition is false (simple form)
        cases: List of if/elif/else cases (cases form)
    """

    name: str
    priority: int = 100
    description: Optional[str] = None
    precondition: Optional[ConditionSpec] = None
    condition: Optional[ConditionSpec] = None
    implies: List[EffectSpec] = []
    otherwise: List[EffectSpec] = []
    cases: List[SolverCaseSpec] = []

    model_config = ConfigDict(extra="forbid")

    @field_validator("precondition", "condition", mode="before")
    @classmethod
    def _parse_condition(cls, value: Any) -> Optional[ConditionSpec]:
        if value is None:
            return None
        return parse_condition_spec(value)

    @field_validator("implies", "otherwise", mode="before")
    @classmethod
    def _parse_effects(cls, value: Any) -> List[EffectSpec]:
        if value is None:
            return []
        if isinstance(value, list):
            return [parse_effect_spec(item) for item in value]
        return [parse_effect_spec(value)]

    @field_validator("cases", mode="before")
    @classmethod
    def _parse_cases(cls, value: Any) -> List[SolverCaseSpec]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("Cases must be a list")
        return [SolverCaseSpec.model_validate(item) for item in value]


def parse_solver_rule_spec(data: Any) -> SolverRuleSpec:
    """Parse a solver rule from raw YAML data."""
    if isinstance(data, SolverRuleSpec):
        return data
    if not isinstance(data, dict):
        raise TypeError("Solver rule entry must be a mapping")
    return SolverRuleSpec.model_validate(data)


def parse_solver_rules(data: Any) -> List[SolverRuleSpec]:
    """Parse a list of solver rules from YAML data."""
    if data is None:
        return []
    if not isinstance(data, list):
        raise TypeError("Solver section must be a list of rules")
    return [parse_solver_rule_spec(item) for item in data]


__all__ = [
    "SolverCaseSpec",
    "SolverRuleSpec",
    "parse_solver_rule_spec",
    "parse_solver_rules",
]
