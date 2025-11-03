from __future__ import annotations

from typing import List

from simulator.core.objects import AttributeTarget

from .base import Effect, StateChange


class TrendEffect(Effect):
    target: AttributeTarget
    direction: str  # up/down/none

    def apply(self, context: "ApplicationContext", instance: "ObjectInstance") -> List[StateChange]:  # noqa: F821
        full_name = context.write_trend(self.target, self.direction, instance)
        return [StateChange(attribute=full_name, before=context._last_before, after=self.direction, kind="trend")]
