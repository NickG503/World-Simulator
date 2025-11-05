"""Space Repository: Clean abstraction for qualitative space access."""

from __future__ import annotations

from typing import List

from simulator.core.attributes.qualitative_space import QualitativeSpace
from simulator.core.registries.registry_manager import RegistryManager


class SpaceRepository:
    """Repository for qualitative space access - clean abstraction over registry."""

    def __init__(self, registry_manager: RegistryManager):
        """
        Initialize space repository.

        Args:
            registry_manager: The registry manager containing spaces
        """
        self.registry_manager = registry_manager

    def get_by_id(self, space_id: str) -> QualitativeSpace:
        """
        Get qualitative space by ID.

        Args:
            space_id: Space identifier

        Returns:
            QualitativeSpace instance

        Raises:
            KeyError: If space not found
        """
        return self.registry_manager.spaces.get(space_id)

    def get_levels(self, space_id: str) -> List[str]:
        """
        Get the ordered levels for a qualitative space.

        Args:
            space_id: Space identifier

        Returns:
            List of level names in order

        Raises:
            KeyError: If space not found
        """
        space = self.get_by_id(space_id)
        return list(space.levels)

    def list_all(self) -> List[str]:
        """
        List all registered qualitative space IDs.

        Returns:
            List of space IDs
        """
        return list(self.registry_manager.spaces.spaces.keys())

    def exists(self, space_id: str) -> bool:
        """
        Check if a qualitative space exists.

        Args:
            space_id: Space identifier

        Returns:
            True if space exists
        """
        try:
            self.get_by_id(space_id)
            return True
        except KeyError:
            return False

    def validate_value(self, space_id: str, value: str) -> bool:
        """
        Check if a value is valid for a given space.

        Args:
            space_id: Space identifier
            value: Value to validate

        Returns:
            True if value is in space's levels
        """
        try:
            space = self.get_by_id(space_id)
            return value in space.levels
        except KeyError:
            return False

    def compare_values(self, space_id: str, value1: str, value2: str) -> int:
        """
        Compare two values in an ordered qualitative space.

        Args:
            space_id: Space identifier
            value1: First value
            value2: Second value

        Returns:
            -1 if value1 < value2, 0 if equal, 1 if value1 > value2

        Raises:
            KeyError: If space not found
            ValueError: If values not in space
        """
        space = self.get_by_id(space_id)
        try:
            idx1 = space.levels.index(value1)
            idx2 = space.levels.index(value2)
            if idx1 < idx2:
                return -1
            elif idx1 > idx2:
                return 1
            else:
                return 0
        except ValueError as e:
            raise ValueError(f"Values '{value1}' or '{value2}' not in space '{space_id}' levels {space.levels}") from e


__all__ = ["SpaceRepository"]
