from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from pydantic import BaseModel, Field

from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.effects.base import Effect
from simulator.core.attributes import AttributeSpec

from .part import PartSpec

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from simulator.core.actions.specs import ConditionSpec as _ConditionSpec
else:  # pragma: no cover - runtime alias
    _ConditionSpec = Any


class ObjectBehavior(BaseModel):
    """Defines object-specific behavior for a generic action."""

    preconditions: List[Condition] = Field(default_factory=list)
    effects: List[Effect] = Field(default_factory=list)

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}


class ObjectConstraint(BaseModel):
    """Structured constraint definition tied to an object type."""

    type: str
    condition: _ConditionSpec | Any | None = None
    requires: _ConditionSpec | Any | None = None

    model_config = {"extra": "allow"}


class ObjectType(BaseModel):
    """Schema for an object with parts hierarchy."""

    name: str
    parts: Dict[str, PartSpec]
    global_attributes: Dict[str, AttributeSpec] = Field(default_factory=dict)
    constraints: List[ObjectConstraint] = Field(default_factory=list)
    behaviors: Dict[str, ObjectBehavior] = Field(default_factory=dict)  # action_name -> behavior
    compiled_constraints: List[Any] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
