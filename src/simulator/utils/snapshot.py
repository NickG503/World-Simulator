from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from simulator.core.objects.object_instance import ObjectInstance


@dataclass(frozen=True)
class ImmutableStateSnapshot:
    """Immutable snapshot of an object's state for diffs."""

    timestamp: datetime
    object_type: str
    attributes: Dict[str, Dict[str, str]]  # part -> attr -> value
    metadata: Dict[str, Any]

    @classmethod
    def from_instance(cls, instance: ObjectInstance) -> "ImmutableStateSnapshot":
        attrs: Dict[str, Dict[str, str]] = {}
        # globals under special key
        attrs["_global"] = {k: v.current_value for k, v in instance.global_attributes.items()}
        for part_name, part in instance.parts.items():
            attrs[part_name] = {k: v.current_value for k, v in part.attributes.items()}
        return cls(
            timestamp=datetime.now(),
            object_type=instance.type.name,
            attributes=attrs,
            metadata={},
        )

    def diff(self, other: "ImmutableStateSnapshot") -> Dict[str, List[Tuple[str, str, str]]]:
        """Return differences as part -> list of (attr, old, new)."""
        differences: Dict[str, List[Tuple[str, str, str]]] = {}
        for part, attrs in self.attributes.items():
            other_attrs = other.attributes.get(part, {})
            for name, value in attrs.items():
                prev = other_attrs.get(name)
                if value != prev:
                    differences.setdefault(part, []).append((name, prev, value))
        return differences
