from __future__ import annotations

from typing import Dict, Generic, Iterable, Tuple, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class VersionedRegistry(BaseModel, Generic[T]):
    items: Dict[Tuple[str, int], T] = Field(default_factory=dict)

    def register(self, name: str, version: int, item: T) -> None:
        key = (name, version)
        if key in self.items:
            raise ValueError(f"Duplicate registration: {name}@v{version}")
        self.items[key] = item

    def get(self, name: str, version: int) -> T:
        key = (name, version)
        if key not in self.items:
            available = ", ".join(f"{n}@v{v}" for n, v in sorted(self.items.keys()))
            raise KeyError(f"Unknown: {name}@v{version}. Available: {available}")
        return self.items[key]

    def all(self) -> Iterable[T]:
        return self.items.values()

    def get_latest(self, name: str) -> T:
        matches = [(v, item) for (n, v), item in self.items.items() if n == name]
        if not matches:
            available_names = sorted({n for (n, _v) in self.items.keys()})
            raise KeyError(f"Unknown: {name}. Available: {', '.join(available_names)}")
        version, item = max(matches, key=lambda x: x[0])
        return item

    def names(self) -> Iterable[str]:
        return sorted({n for (n, _v) in self.items.keys()})


class NameRegistry(BaseModel, Generic[T]):
    items: Dict[str, T] = Field(default_factory=dict)

    def register(self, name: str, item: T) -> None:
        if name in self.items:
            raise ValueError(f"Duplicate registration: {name}")
        self.items[name] = item

    def get(self, name: str) -> T:
        if name not in self.items:
            available = ", ".join(sorted(self.items.keys()))
            raise KeyError(f"Unknown: {name}. Available: {available}")
        return self.items[name]

    def all(self) -> Iterable[T]:
        return self.items.values()

    def names(self) -> Iterable[str]:
        return sorted(self.items.keys())
