from __future__ import annotations
from typing import Any, Dict
from pydantic import BaseModel
from simulator.core.objects import AttributeTarget, ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager


class EvaluationContext(BaseModel):
    instance: ObjectInstance
    action: Any
    parameters: Dict[str, Any]
    registries: RegistryManager

    model_config = {"arbitrary_types_allowed": True}

    def read_attribute(self, target: AttributeTarget) -> str:
        if target.part is None:
            if target.attribute not in self.instance.global_attributes:
                raise KeyError(f"Global attribute not found: {target.attribute}")
            return self.instance.global_attributes[target.attribute].current_value  # type: ignore
        if target.part not in self.instance.parts:
            raise KeyError(f"Part not found: {target.part}")
        part = self.instance.parts[target.part]
        if target.attribute not in part.attributes:
            raise KeyError(f"Attribute not found: {target.part}.{target.attribute}")
        return part.attributes[target.attribute].current_value  # type: ignore


class ApplicationContext(EvaluationContext):
    # helpers for writing and tracking 'before' values for change recording
    # instance-scoped (not class-level) to avoid shared mutable state
    _last_before: str | None = None

    def write_attribute(self, target: AttributeTarget, value: str, instance: ObjectInstance) -> str:
        # Resolve attribute safely and validate value against its qualitative space
        if target.part is None:
            if target.attribute not in instance.global_attributes:
                raise KeyError(f"Global attribute not found: {target.attribute}")
            ai = instance.global_attributes[target.attribute]
        else:
            if target.part not in instance.parts:
                raise KeyError(f"Part not found: {target.part}")
            part = instance.parts[target.part]
            if target.attribute not in part.attributes:
                raise KeyError(f"Attribute not found: {target.part}.{target.attribute}")
            ai = part.attributes[target.attribute]

        # Validate value belongs to the attribute's space
        space = self.registries.spaces.get(ai.spec.space_id)
        if value not in space.levels:
            raise ValueError(
                f"Invalid value '{value}' for {target.to_string()}. Valid values: {space.levels}"
            )

        # Record before and apply
        self._last_before = ai.current_value if isinstance(ai.current_value, str) else None
        ai.current_value = value
        return target.attribute if target.part is None else f"{target.part}.{target.attribute}"

    def write_trend(self, target: AttributeTarget, direction: str, instance: ObjectInstance) -> str:
        # Resolve attribute safely and set trend direction (no space validation for trend)
        if target.part is None:
            if target.attribute not in instance.global_attributes:
                raise KeyError(f"Global attribute not found: {target.attribute}")
            ai = instance.global_attributes[target.attribute]
            before = ai.trend or "none"
            self._last_before = before
            ai.trend = direction  # type: ignore
            return f"{target.attribute}.trend"
        if target.part not in instance.parts:
            raise KeyError(f"Part not found: {target.part}")
        part = instance.parts[target.part]
        if target.attribute not in part.attributes:
            raise KeyError(f"Attribute not found: {target.part}.{target.attribute}")
        ai = part.attributes[target.attribute]
        before = ai.trend or "none"
        self._last_before = before
        ai.trend = direction  # type: ignore
        return f"{target.part}.{target.attribute}.trend"
