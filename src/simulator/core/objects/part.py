from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from pydantic import BaseModel

from simulator.core.attributes import AttributeInstance, AttributeSpec

if TYPE_CHECKING:
    from simulator.core.objects.object_instance import ObjectInstance


class PartSpec(BaseModel):
    """Specification for a part of an object."""

    name: str
    attributes: Dict[str, AttributeSpec]


class PartInstance(BaseModel):
    """Runtime instance of a part."""

    spec: PartSpec
    attributes: Dict[str, AttributeInstance]


class AttributeTarget(BaseModel):
    """Reference to a concrete attribute on an instance.

    The target can be global (no part) or part-qualified like 'switch.position'.
    """

    part: Optional[str] = None
    attribute: str

    @classmethod
    def from_string(cls, ref: str) -> "AttributeTarget":
        """Parse 'part.attribute' or 'attribute' strings with basic validation."""
        if not isinstance(ref, str):
            raise ValueError(f"Invalid attribute reference (not a string): {ref!r}")
        text = ref.strip()
        if not text:
            raise ValueError("Empty attribute reference")
        if "." in text:
            p, a = text.split(".", 1)
            p = p.strip()
            a = a.strip()
            if not p or not a:
                raise ValueError(f"Invalid attribute reference format: {ref!r}")
            return cls(part=p, attribute=a)
        return cls(part=None, attribute=text)

    def to_string(self) -> str:
        if self.part:
            return f"{self.part}.{self.attribute}"
        return self.attribute

    def resolve(self, instance: "ObjectInstance") -> AttributeInstance:
        """Resolve this target to an AttributeInstance on the given object instance."""
        from simulator.core.objects.object_instance import ObjectInstance  # local import to avoid cycle

        if not isinstance(instance, ObjectInstance):  # defensive
            raise TypeError("resolve() expects an ObjectInstance")

        if self.part is None:
            if self.attribute not in instance.global_attributes:
                available = ", ".join(sorted(instance.global_attributes.keys()))
                raise KeyError(f"Global attribute not found: '{self.attribute}'. Available: {available}")
            return instance.global_attributes[self.attribute]

        if self.part not in instance.parts:
            available_parts = ", ".join(sorted(instance.parts.keys()))
            raise KeyError(f"Part not found: '{self.part}'. Available parts: {available_parts}")
        part = instance.parts[self.part]
        if self.attribute not in part.attributes:
            available_attrs = ", ".join(sorted(part.attributes.keys()))
            raise KeyError(f"Attribute not found: '{self.part}.{self.attribute}'. Available: {available_attrs}")
        return part.attributes[self.attribute]
