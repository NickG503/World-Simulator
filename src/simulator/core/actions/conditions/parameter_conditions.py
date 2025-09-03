from __future__ import annotations
from typing import List
from pydantic import BaseModel
from .base import Condition


class ParameterValid(Condition):
    parameter: str
    valid_values: List[str]

    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        val = context.parameters.get(self.parameter)
        return val in self.valid_values
    
    def describe(self) -> str:
        return f"parameter '{self.parameter}' in {self.valid_values}"


class ParameterEquals(Condition):
    parameter: str
    value: str

    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        return context.parameters.get(self.parameter) == self.value
    
    def describe(self) -> str:
        return f"parameter '{self.parameter}' == '{self.value}'"

