from __future__ import annotations
from typing import Dict
from pydantic import BaseModel
from simulator.core.objects.object_type import ObjectType
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.objects import AttributeTarget
from simulator.core.registries.registry_manager import RegistryManager
from simulator.io.loaders.object_loader import instantiate_default
from simulator.core.constraints import ConstraintEngine


class ObjectInstanceBuilder(BaseModel):
    """Builder for creating object instances with validation and overrides."""

    object_type: ObjectType
    registries: RegistryManager
    instance: ObjectInstance

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def for_type(cls, object_type: ObjectType, registries: RegistryManager) -> "ObjectInstanceBuilder":
        inst = instantiate_default(object_type, registries)
        return cls(object_type=object_type, registries=registries, instance=inst)

    def set_attribute(self, target: str, value: str) -> "ObjectInstanceBuilder":
        tgt = AttributeTarget.from_string(target)
        ai = tgt.resolve(self.instance)
        space = self.registries.spaces.get(ai.spec.space_id)
        if value not in space.levels:
            raise ValueError(f"Invalid value '{value}' for {target}; valid: {space.levels}")
        ai.current_value = value
        return self

    def set_attributes(self, mapping: Dict[str, str]) -> "ObjectInstanceBuilder":
        for k, v in mapping.items():
            self.set_attribute(k, v)
        return self

    def build(self) -> ObjectInstance:
        # Basic constraint validation (object-level constraints)
        ce = ConstraintEngine()
        constraints = [ce.create_constraint(c.model_dump()) for c in self.object_type.constraints]
        violations = ce.validate_instance(self.instance, constraints)
        if violations:
            raise ValueError("Instance violates constraints: " + "; ".join(str(v) for v in violations))
        return self.instance

