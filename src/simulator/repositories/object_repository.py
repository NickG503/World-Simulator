"""Object Repository: Clean abstraction for object type access."""

from __future__ import annotations

from typing import Dict, List

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.objects.object_type import ObjectType
from simulator.core.registries.registry_manager import RegistryManager


class ObjectRepository:
    """Repository for object type access - clean abstraction over registry."""

    def __init__(self, registry_manager: RegistryManager):
        """
        Initialize object repository.

        Args:
            registry_manager: The registry manager containing object types
        """
        self.registry_manager = registry_manager

    def get_by_name(self, name: str) -> ObjectType:
        """
        Get object type by name.

        Args:
            name: Object type name

        Returns:
            ObjectType instance

        Raises:
            KeyError: If object type not found
        """
        return self.registry_manager.objects.get(name)

    def get_default_instance(self, name: str) -> ObjectInstance:
        """
        Get a default instance of an object type.

        Args:
            name: Object type name

        Returns:
            Default ObjectInstance

        Raises:
            KeyError: If object type not found
        """
        from simulator.io.loaders.object_loader import instantiate_default

        obj_type = self.get_by_name(name)
        return instantiate_default(obj_type, self.registry_manager)

    def list_all(self) -> List[str]:
        """
        List all registered object type names.

        Returns:
            List of object type names
        """
        return list(self.registry_manager.objects.all())

    def exists(self, name: str) -> bool:
        """
        Check if an object type exists.

        Args:
            name: Object type name

        Returns:
            True if object type exists
        """
        try:
            self.get_by_name(name)
            return True
        except KeyError:
            return False

    def get_behaviors(self, name: str) -> Dict[str, any]:
        """
        Get behaviors for an object type.

        Args:
            name: Object type name

        Returns:
            Dict of behavior name to ObjectBehavior

        Raises:
            KeyError: If object type not found
        """
        obj_type = self.get_by_name(name)
        return obj_type.behaviors

    def has_behavior(self, object_name: str, behavior_name: str) -> bool:
        """
        Check if an object has a specific behavior.

        Args:
            object_name: Object type name
            behavior_name: Behavior (action) name

        Returns:
            True if object has the behavior
        """
        try:
            obj_type = self.get_by_name(object_name)
            return behavior_name in obj_type.behaviors
        except KeyError:
            return False


__all__ = ["ObjectRepository"]
