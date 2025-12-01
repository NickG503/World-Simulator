from __future__ import annotations

"""Shared parsing helpers for action conditions and effects.

This module provides a single authoritative place to translate the raw YAML
structures used across actions, object behaviors, and constraints into the
runtime `Condition` and `Effect` instances consumed by the simulator.

NOTE: Simplified for tree-based simulation. Complex logical conditions
(AND/OR/NOT/Implication) have been removed. Preconditions are now binary
(single AttributeCondition). Postconditions use flat if-elif-else in effects.
"""

from typing import Any, Dict, Iterable, List, Literal, Mapping, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from simulator.core.actions.condition_registry import get_condition_registry
from simulator.core.actions.conditions.attribute_conditions import (
    AttributeCondition,
    ComparisonOperator,
)
from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.conditions.parameter_conditions import (
    ParameterEquals,
    ParameterValid,
)
from simulator.core.actions.effect_registry import get_effect_registry
from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
from simulator.core.actions.effects.base import Effect
from simulator.core.actions.effects.conditional_effects import ConditionalEffect
from simulator.core.actions.effects.trend_effects import TrendEffect
from simulator.core.actions.parameter import ParameterReference
from simulator.core.objects import AttributeTarget

# ---------------------------------------------------------------------------
# Pydantic specs
# ---------------------------------------------------------------------------


class _BaseSpec(BaseModel):
    """Base settings shared by all spec models."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ConditionSpec(_BaseSpec):
    type: str


class ParameterValidConditionSpec(ConditionSpec):
    type: Literal["parameter_valid"]
    parameter: str
    valid_values: List[str] = Field(default_factory=list)


class ParameterEqualsConditionSpec(ConditionSpec):
    type: Literal["parameter_equals"]
    parameter: str
    value: Any

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> str:
        return str(value)


class AttributeCheckConditionSpec(ConditionSpec):
    type: Literal["attribute_check"]
    target: str
    operator: ComparisonOperator
    value: Any


ConditionSpec.model_rebuild()


class EffectSpec(_BaseSpec):
    type: str


class SetAttributeEffectSpec(EffectSpec):
    type: Literal["set_attribute"]
    target: str
    value: Any


class SetTrendEffectSpec(EffectSpec):
    type: Literal["set_trend"]
    target: str
    direction: Literal["up", "down", "none"]


class ConditionalEffectSpec(EffectSpec):
    type: Literal["conditional"]
    condition: ConditionSpec
    then_effects: List[EffectSpec] = Field(alias="then")
    else_effects: List[EffectSpec] = Field(default_factory=list, alias="else")

    @field_validator("condition", mode="before")
    @classmethod
    def _parse_condition_field(cls, value: Any) -> ConditionSpec:
        return parse_condition_spec(value)

    @field_validator("then_effects", "else_effects", mode="before")
    @classmethod
    def _parse_effects(cls, value: Any) -> List[EffectSpec]:
        if value is None:
            items: List[Any] = []
        elif isinstance(value, dict):
            items = [value]
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            items = list(value)
        else:
            raise TypeError("Conditional effect branches must be a mapping or list")
        return [parse_effect_spec(item) for item in items]


ConditionalEffectSpec.model_rebuild()


# ---------------------------------------------------------------------------
# Registry initialization - register all built-in types
# ---------------------------------------------------------------------------


def _register_builtin_types() -> None:
    """Register all built-in condition and effect types."""
    condition_registry = get_condition_registry()
    effect_registry = get_effect_registry()

    # Register condition types - simplified to just attribute checks and parameter conditions
    condition_registry.register(
        "parameter_valid", ParameterValidConditionSpec, lambda spec: _build_parameter_valid(spec)
    )
    condition_registry.register(
        "parameter_equals", ParameterEqualsConditionSpec, lambda spec: _build_parameter_equals(spec)
    )
    condition_registry.register(
        "attribute_check", AttributeCheckConditionSpec, lambda spec: _build_attribute_condition(spec)
    )

    # Register effect types
    effect_registry.register("set_attribute", SetAttributeEffectSpec, lambda spec: _build_set_attribute_effect(spec))
    effect_registry.register("set_trend", SetTrendEffectSpec, lambda spec: _build_set_trend_effect(spec))
    effect_registry.register("conditional", ConditionalEffectSpec, lambda spec: _build_conditional_effect(spec))


# Register built-in types on module load
_register_builtin_types()


# ---------------------------------------------------------------------------
# Shared normalization helpers
# ---------------------------------------------------------------------------


def _ensure_mapping(value: Any, ctx: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Expected mapping for {ctx}, got {type(value).__name__}")
    return value


def _normalize_attribute_value(raw: Any) -> Union[str, ParameterReference]:
    """Normalize attribute values used in conditions/effects."""

    if isinstance(raw, ParameterReference):
        return raw
    if isinstance(raw, dict) and raw.get("type") == "parameter_ref":
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("parameter_ref requires a non-empty 'name'")
        return ParameterReference(name=name.strip())
    if isinstance(raw, bool):
        return "on" if raw else "off"
    return str(raw)


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def parse_condition_spec(data: Any) -> ConditionSpec:
    """Parse condition data using the condition registry."""
    if isinstance(data, ConditionSpec):
        return data
    mapping = _ensure_mapping(data, "condition")
    condition_registry = get_condition_registry()
    return condition_registry.parse_spec(mapping)


def parse_effect_spec(data: Any) -> EffectSpec:
    """Parse effect data using the effect registry."""
    if isinstance(data, EffectSpec):
        return data
    mapping = _ensure_mapping(data, "effect")
    effect_registry = get_effect_registry()
    return effect_registry.parse_spec(mapping)


# ---------------------------------------------------------------------------
# Runtime builders - Individual builder functions for each type
# ---------------------------------------------------------------------------


def _build_parameter_valid(spec: ParameterValidConditionSpec) -> Condition:
    """Build ParameterValid condition from spec."""
    return ParameterValid(parameter=spec.parameter, valid_values=list(spec.valid_values))


def _build_parameter_equals(spec: ParameterEqualsConditionSpec) -> Condition:
    """Build ParameterEquals condition from spec."""
    return ParameterEquals(parameter=spec.parameter, value=str(spec.value))


def _build_attribute_condition(spec: AttributeCheckConditionSpec) -> Condition:
    """Build AttributeCondition from spec."""
    target = AttributeTarget.from_string(spec.target)
    value = _normalize_attribute_value(spec.value)
    return AttributeCondition(target=target, operator=spec.operator, value=value)  # type: ignore[arg-type]


def _build_set_attribute_effect(spec: SetAttributeEffectSpec) -> Effect:
    """Build SetAttributeEffect from spec."""
    target = AttributeTarget.from_string(spec.target)
    value = _normalize_attribute_value(spec.value)
    return SetAttributeEffect(target=target, value=value)  # type: ignore[arg-type]


def _build_set_trend_effect(spec: SetTrendEffectSpec) -> Effect:
    """Build TrendEffect from spec."""
    target = AttributeTarget.from_string(spec.target)
    return TrendEffect(target=target, direction=spec.direction)


def _build_conditional_effect(spec: ConditionalEffectSpec) -> Effect:
    """Build ConditionalEffect from spec."""
    cond = build_condition(spec.condition)
    then_effects = [build_effect(e) for e in spec.then_effects]
    else_effects = [build_effect(e) for e in spec.else_effects]
    return ConditionalEffect(condition=cond, then_effect=then_effects, else_effect=else_effects)


def build_condition(spec: ConditionSpec) -> Condition:
    """Build runtime condition from spec."""
    if isinstance(spec, ParameterValidConditionSpec):
        return _build_parameter_valid(spec)
    if isinstance(spec, ParameterEqualsConditionSpec):
        return _build_parameter_equals(spec)
    if isinstance(spec, AttributeCheckConditionSpec):
        return _build_attribute_condition(spec)
    raise TypeError(f"Unsupported condition spec: {spec}")


def build_effect(spec: EffectSpec) -> Effect:
    """Build runtime effect from spec."""
    if isinstance(spec, SetAttributeEffectSpec):
        return _build_set_attribute_effect(spec)
    if isinstance(spec, SetTrendEffectSpec):
        return _build_set_trend_effect(spec)
    if isinstance(spec, ConditionalEffectSpec):
        return _build_conditional_effect(spec)
    raise TypeError(f"Unsupported effect spec: {spec}")


def build_condition_from_raw(data: Any) -> Condition:
    """Convenience helper accepting raw mappings or pre-built conditions."""

    if isinstance(data, Condition):
        return data
    spec = parse_condition_spec(data)
    return build_condition(spec)


def build_effect_from_raw(data: Any) -> Effect:
    if isinstance(data, Effect):
        return data
    spec = parse_effect_spec(data)
    return build_effect(spec)


def build_conditions(raw_items: Iterable[Any]) -> List[Condition]:
    return [build_condition_from_raw(item) for item in raw_items]


def build_effects(raw_items: Iterable[Any]) -> List[Effect]:
    return [build_effect_from_raw(item) for item in raw_items]


def parse_preconditions_field(value: Any) -> List[ConditionSpec]:
    """Normalize precondition declarations from YAML into structured specs.

    Simplified: Only accepts a list of simple conditions (no nested AND/OR).
    """
    if value is None:
        return []

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
        return [parse_condition_spec(item) for item in value]

    if isinstance(value, Mapping):
        return [parse_condition_spec(value)]

    if isinstance(value, ConditionSpec):
        return [value]

    return [parse_condition_spec(value)]


__all__ = [
    "AttributeCheckConditionSpec",
    "ConditionalEffectSpec",
    "ParameterEqualsConditionSpec",
    "ParameterValidConditionSpec",
    "SetAttributeEffectSpec",
    "SetTrendEffectSpec",
    "build_condition",
    "build_condition_from_raw",
    "build_conditions",
    "build_effect",
    "build_effect_from_raw",
    "build_effects",
    "parse_preconditions_field",
    "parse_condition_spec",
    "parse_effect_spec",
]
