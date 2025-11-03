from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel

from .conditions.base import Condition
from .effects.base import Effect
from .parameter import ParameterSpec


class ActionMetadata(BaseModel):
    description: str | None = None


class Action(BaseModel):
    """Structured action definition."""

    name: str
    object_type: str  # generic, object-specific, etc.
    parameters: Dict[str, ParameterSpec]
    preconditions: List[Condition]
    effects: List[Effect]
    metadata: ActionMetadata | None = None

    def is_generic(self) -> bool:
        """Check if this is a generic action."""
        return self.object_type.lower() == "generic"
