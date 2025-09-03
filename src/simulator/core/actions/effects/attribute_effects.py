from __future__ import annotations
from typing import List, Union
from .base import Effect, StateChange
from simulator.core.objects import AttributeTarget
from simulator.core.actions.parameter import ParameterReference


class SetAttributeEffect(Effect):
    """Set an attribute to a specific value."""

    target: AttributeTarget
    value: Union[str, ParameterReference]

    def apply(self, context: "ApplicationContext", instance: "ObjectInstance") -> List[StateChange]:  # noqa: F821
        from simulator.core.engine.context import ApplicationContext  # local import
        assert context is not None

        # Resolve value
        if isinstance(self.value, ParameterReference):
            new_val = context.parameters.get(self.value.name)
        else:
            new_val = self.value

        full_name = context.write_attribute(self.target, new_val, instance)
        return [StateChange(attribute=full_name, before=context._last_before, after=new_val, kind="value")]

