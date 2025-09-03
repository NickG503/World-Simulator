from __future__ import annotations
from typing import List
from pydantic import BaseModel
from simulator.core.actions.effects.base import Effect, StateChange
from .context import ApplicationContext
from simulator.core.objects.object_instance import ObjectInstance


class EffectApplier(BaseModel):
    def apply(self, effect: Effect, context: ApplicationContext, new_instance: ObjectInstance) -> List[StateChange]:
        return effect.apply(context, new_instance)

