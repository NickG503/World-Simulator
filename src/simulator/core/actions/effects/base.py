from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from pydantic import BaseModel


class StateChange(BaseModel):
    """Record of a change during effect application."""

    attribute: str  # target reference, e.g., "switch.position" or "battery.level.trend"
    before: str | None
    after: str | None
    kind: str  # "value" or "trend"


class Effect(BaseModel, ABC):
    """Base class for all effects."""

    @abstractmethod
    def apply(self, context: "ApplicationContext", instance: "ObjectInstance") -> List[StateChange]:  # noqa: F821
        raise NotImplementedError
