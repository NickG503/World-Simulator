from __future__ import annotations
from typing import List, Literal
from .base import Condition


LogicalOperator = Literal["and", "or", "not"]


class LogicalCondition(Condition):
    operator: LogicalOperator
    conditions: List[Condition]

    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        if self.operator == "and":
            return all(c.evaluate(context) for c in self.conditions)
        if self.operator == "or":
            return any(c.evaluate(context) for c in self.conditions)
        if self.operator == "not":
            if len(self.conditions) != 1:
                raise ValueError("NOT requires exactly one condition")
            return not self.conditions[0].evaluate(context)
        raise ValueError(f"Unknown logical operator: {self.operator}")

    def describe(self) -> str:
        if self.operator == "not":
            return f"NOT ({self.conditions[0].describe()})"
        elif self.operator in ("and", "or"):
            join_str = f" {self.operator.upper()} "
            return "(" + join_str.join(c.describe() for c in self.conditions) + ")"
        return f"{self.operator}({[c.describe() for c in self.conditions]})"


class ImplicationCondition(Condition):
    if_condition: Condition
    then_condition: Condition

    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        # (not A) or B
        return (not self.if_condition.evaluate(context)) or self.then_condition.evaluate(context)
    
    def describe(self) -> str:
        return f"IF ({self.if_condition.describe()}) THEN ({self.then_condition.describe()})"

