from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .parameter import ParameterSpec
from .conditions.base import Condition
from .effects.base import Effect


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
