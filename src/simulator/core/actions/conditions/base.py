from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel


class Condition(BaseModel, ABC):
    """Base class for all conditions."""

    @abstractmethod
    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        raise NotImplementedError

    def describe(self) -> str:
        return self.__class__.__name__

