from __future__ import annotations
from typing import List, Sequence
from .base import Effect, StateChange
from simulator.core.actions.conditions.base import Condition


class ConditionalEffect(Effect):
    condition: Condition
    then_effect: Effect | List[Effect]
    else_effect: Effect | List[Effect] | None = None

    def _as_list(self, eff: Effect | List[Effect] | None) -> List[Effect]:
        if eff is None:
            return []
        return eff if isinstance(eff, list) else [eff]

    def apply(self, context: "ApplicationContext", instance: "ObjectInstance") -> List[StateChange]:  # noqa: F821
        if self.condition.evaluate(context):
            effects = self._as_list(self.then_effect)
        else:
            effects = self._as_list(self.else_effect)
        changes: List[StateChange] = []
        for e in effects:
            changes.extend(e.apply(context, instance))
        return changes

