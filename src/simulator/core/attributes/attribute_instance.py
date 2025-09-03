from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel
from .attribute_spec import AttributeSpec


class AttributeInstance(BaseModel):
    """Runtime instance of an attribute with current state."""

    spec: AttributeSpec
    current_value: Union[str, Literal["unknown"]]
    trend: Optional[Literal["up", "down", "none"]] = None
    confidence: float = 1.0

