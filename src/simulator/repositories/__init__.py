"""Repository Layer: Clean abstractions for data access."""

from __future__ import annotations

from .action_repository import ActionRepository
from .object_repository import ObjectRepository
from .space_repository import SpaceRepository

__all__ = [
    "ActionRepository",
    "ObjectRepository",
    "SpaceRepository",
]
