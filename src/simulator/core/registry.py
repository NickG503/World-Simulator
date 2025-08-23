from __future__ import annotations
from typing import Dict, Tuple, Iterable
from simulator.core.object_types import ObjectType


class Registry:
    """In-memory registry of object types by (name, version)."""
    def __init__(self) -> None:
        self._types: Dict[Tuple[str, int], ObjectType] = {}

    def add_object_type(self, obj_type: ObjectType) -> None:
        key = (obj_type.name, obj_type.version)
        if key in self._types:
            raise ValueError(f"Duplicate type registration: {obj_type.name}@v{obj_type.version}")
        self._types[key] = obj_type

    def get(self, name: str, version: int) -> ObjectType:
        key = (name, version)
        if key not in self._types:
            raise KeyError(f"Unknown object type {name}@v{version}")
        return self._types[key]

    def all(self) -> Iterable[ObjectType]:
        return self._types.values()