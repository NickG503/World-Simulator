from __future__ import annotations

"""Schema definitions for object YAML files."""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from simulator.core.actions.specs import (
    ConditionSpec,
    EffectSpec,
    build_condition,
    build_effect,
    parse_effect_spec,
    parse_preconditions_field,
)
from simulator.core.attributes import AttributeSpec
from simulator.core.constraints.specs import ConstraintSpec, parse_constraint_spec
from simulator.core.objects import PartSpec
from simulator.core.objects.object_type import ObjectBehavior, ObjectConstraint, ObjectType


class AttributeDefinitionSpec(BaseModel):
    space: str
    mutable: bool = True
    default: Optional[str] = None

    def build(self, name: str) -> AttributeSpec:
        return AttributeSpec(
            name=name,
            space_id=self.space,
            mutable=self.mutable,
            default_value=self.default,
        )


class PartDefinitionSpec(BaseModel):
    attributes: Dict[str, AttributeDefinitionSpec] = Field(default_factory=dict)

    def build(self, name: str) -> PartSpec:
        attrs = {attr_name: spec.build(attr_name) for attr_name, spec in self.attributes.items()}
        return PartSpec(name=name, attributes=attrs)


class BehaviorDefinitionSpec(BaseModel):
    preconditions: List[ConditionSpec] = Field(default_factory=list)
    effects: List[EffectSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    @field_validator("preconditions", mode="before")
    @classmethod
    def _parse_preconditions(cls, value):
        return parse_preconditions_field(value)

    @field_validator("effects", mode="before")
    @classmethod
    def _parse_effects(cls, value):
        if value is None:
            return []
        return [parse_effect_spec(item) for item in value]

    def build(self) -> ObjectBehavior:
        extras = dict(self.model_extra or {})  # type: ignore[attr-defined]
        return ObjectBehavior(
            preconditions=[build_condition(cond) for cond in self.preconditions],
            effects=[build_effect(effect) for effect in self.effects],
            **extras,
        )


class ObjectFileSpec(BaseModel):
    type: str
    parts: Dict[str, PartDefinitionSpec] = Field(default_factory=dict)
    global_attributes: Dict[str, AttributeDefinitionSpec] = Field(default_factory=dict)
    constraints: List[ConstraintSpec] = Field(default_factory=list)
    behaviors: Dict[str, BehaviorDefinitionSpec] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @field_validator("constraints", mode="before")
    @classmethod
    def _parse_constraints(cls, value):
        if value is None:
            return []
        return [parse_constraint_spec(item) for item in value]

    def build_object_type(self) -> ObjectType:
        parts = {name: spec.build(name) for name, spec in self.parts.items()}
        global_attrs = {name: spec.build(name) for name, spec in self.global_attributes.items()}

        constraints: List[ObjectConstraint] = []
        compiled_constraints = []
        for spec in self.constraints:
            extras = dict(spec.model_extra or {})  # type: ignore[attr-defined]
            constraint = ObjectConstraint(
                type=spec.type,
                condition=getattr(spec, "condition", None),
                requires=getattr(spec, "requires", None),
                **extras,
            )
            constraints.append(constraint)
            compiled_constraints.append(self._compile_constraint(constraint))

        behaviors: Dict[str, ObjectBehavior] = {}
        for name, spec in self.behaviors.items():
            behaviors[name] = spec.build()

        return ObjectType(
            name=self.type.strip(),
            parts=parts,
            global_attributes=global_attrs,
            constraints=constraints,
            behaviors=behaviors,
            compiled_constraints=compiled_constraints,
        )

    @staticmethod
    def _compile_constraint(constraint: ObjectConstraint):
        from simulator.core.constraints.constraint import DependencyConstraint

        if constraint.type == "dependency":
            if constraint.condition is None or constraint.requires is None:
                raise ValueError("dependency constraint requires both 'condition' and 'requires'")
            condition = build_condition(constraint.condition)
            requires = build_condition(constraint.requires)
            return DependencyConstraint(condition=condition, requires=requires)
        raise ValueError(f"Unsupported constraint type: {constraint.type}")


__all__ = [
    "ObjectFileSpec",
    "BehaviorDefinitionSpec",
    "PartDefinitionSpec",
    "AttributeDefinitionSpec",
]
