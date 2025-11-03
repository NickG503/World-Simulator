from __future__ import annotations

from pydantic import BaseModel

from simulator.core.actions.conditions.base import Condition

from .context import EvaluationContext


class ConditionEvaluator(BaseModel):
    def evaluate(self, condition: Condition, context: EvaluationContext) -> bool:
        return condition.evaluate(context)
