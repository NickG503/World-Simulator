from __future__ import annotations
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field
from .parameter import ParameterSpec
from .conditions.base import Condition
from .effects.base import Effect


class ActionMetadata(BaseModel):
    description: str | None = None


class Action(BaseModel):
    """Structured action definition."""

    name: str
    object_type: str  # Keep for backward compatibility, but also support capabilities
    required_capabilities: Set[str] = Field(default_factory=set)  # New: capabilities this action needs
    parameters: Dict[str, ParameterSpec]
    preconditions: List[Condition]
    effects: List[Effect]
    metadata: ActionMetadata | None = None
    
    def is_capability_based(self) -> bool:
        """Check if this is a capability-based action."""
        return bool(self.required_capabilities)
    
    def is_generic(self) -> bool:
        """Check if this is a generic action (backward compatibility)."""
        return self.object_type.lower() == "generic"
