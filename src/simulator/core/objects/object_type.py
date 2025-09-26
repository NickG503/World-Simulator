from __future__ import annotations
from typing import Dict, List, TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from .part import PartSpec
from simulator.core.attributes import AttributeSpec
from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.effects.base import Effect

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from simulator.core.constraints.constraint import Constraint
    from simulator.core.actions.specs import ConditionSpec as _ConditionSpec
else:  # pragma: no cover - runtime alias
    _ConditionSpec = Any


class ObjectBehavior(BaseModel):
    """Defines object-specific behavior for a generic action."""

    preconditions: List[Condition] = Field(default_factory=list)
    effects: List[Effect] = Field(default_factory=list)

    # Allow additional fields for future extensions while storing runtime models
    model_config = {"extra": "allow", "arbitrary_types_allowed": True}


class ObjectConstraint(BaseModel):
    """Structured constraint definition tied to an object type."""

    type: str
    condition: _ConditionSpec | Any | None = None
    requires: _ConditionSpec | Any | None = None

    # Allow additional fields for different constraint types
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
