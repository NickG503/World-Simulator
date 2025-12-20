"""Attribute path utilities for resolving part.attribute paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:
    from simulator.core.attributes import AttributeInstance
    from simulator.core.objects.object_instance import ObjectInstance
    from simulator.core.simulation_runner import AttributeSnapshot
    from simulator.core.tree.models import WorldSnapshot


@dataclass
class AttributePath:
    """Parses and resolves attribute paths like 'battery.level' or 'power'."""

    part: Optional[str]
    attribute: str

    @classmethod
    def parse(cls, path: str) -> "AttributePath":
        """Parse a path string into an AttributePath."""
        parts = path.split(".")
        if len(parts) == 2:
            return cls(part=parts[0], attribute=parts[1])
        elif len(parts) == 1:
            return cls(part=None, attribute=parts[0])
        else:
            raise ValueError(f"Invalid attribute path: {path}")

    def to_string(self) -> str:
        """Convert back to string form."""
        if self.part:
            return f"{self.part}.{self.attribute}"
        return self.attribute

    @property
    def is_global(self) -> bool:
        """Check if this is a global attribute (no part)."""
        return self.part is None

    def resolve_from_instance(self, instance: "ObjectInstance") -> Optional["AttributeInstance"]:
        """Resolve to an AttributeInstance from an ObjectInstance."""
        if self.part is None:
            return instance.global_attributes.get(self.attribute)
        part_inst = instance.parts.get(self.part)
        if part_inst:
            return part_inst.attributes.get(self.attribute)
        return None

    def resolve_from_snapshot(self, snapshot: "WorldSnapshot") -> Optional["AttributeSnapshot"]:
        """Resolve to an AttributeSnapshot from a WorldSnapshot."""
        if self.part is None:
            return snapshot.object_state.global_attributes.get(self.attribute)
        part = snapshot.object_state.parts.get(self.part)
        if part:
            return part.attributes.get(self.attribute)
        return None

    def get_value_from_snapshot(self, snapshot: "WorldSnapshot") -> Union[str, List[str], None]:
        """Get attribute value from a snapshot."""
        attr = self.resolve_from_snapshot(snapshot)
        return attr.value if attr else None

    def set_value_in_snapshot(self, snapshot: "WorldSnapshot", value: Any) -> None:
        """Set attribute value in a snapshot (in place)."""
        attr = self.resolve_from_snapshot(snapshot)
        if attr:
            attr.value = value

    def set_value_in_instance(self, instance: "ObjectInstance", value: str) -> None:
        """Set attribute value in an instance."""
        attr = self.resolve_from_instance(instance)
        if attr:
            attr.current_value = value

    def get_value_from_instance(self, instance: "ObjectInstance") -> Optional[str]:
        """Get attribute value from an instance."""
        attr = self.resolve_from_instance(instance)
        return attr.current_value if attr else None
