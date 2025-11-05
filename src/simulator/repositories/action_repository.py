"""Action Repository: Clean abstraction for action access and lookup."""

from __future__ import annotations

from typing import List, Optional

from simulator.core.actions.action import Action
from simulator.core.registries.registry_manager import RegistryManager


class ActionRepository:
    """Repository for action access - clean abstraction over registry."""

    def __init__(self, registry_manager: RegistryManager):
        """
        Initialize action repository.

        Args:
            registry_manager: The registry manager containing actions
        """
        self.registry_manager = registry_manager

    def find_for_object(self, object_name: str, action_name: str) -> Optional[Action]:
        """
        Find the appropriate action for an object.

        This encapsulates the logic of finding generic vs object-specific actions.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            Action if found, None otherwise
        """
        return self.registry_manager.find_action_for_object(object_name, action_name)

    def get_enhanced_action(self, object_name: str, action_name: str) -> Optional[Action]:
        """
        Get action enhanced with object-specific behavior if available.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            Enhanced Action if found, None otherwise
        """
        return self.registry_manager.create_behavior_enhanced_action(object_name, action_name)

    def get_generic(self, action_name: str) -> Optional[Action]:
        """
        Get a generic action by name.

        Args:
            action_name: Action name

        Returns:
            Action if found, None otherwise
        """
        key = f"generic/{action_name}"
        try:
            return self.registry_manager.actions.get(key)
        except KeyError:
            return None

    def get_specific(self, object_name: str, action_name: str) -> Optional[Action]:
        """
        Get an object-specific action.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            Action if found, None otherwise
        """
        key = f"{object_name}/{action_name}"
        try:
            return self.registry_manager.actions.get(key)
        except KeyError:
            return None

    def list_for_object(self, object_name: str) -> List[str]:
        """
        List all actions available for an object (generic + object-specific + behaviors).

        Args:
            object_name: Object type name

        Returns:
            List of action names
        """
        actions = set()

        # Get object behaviors
        try:
            obj_type = self.registry_manager.objects.get(object_name)
            actions.update(obj_type.behaviors.keys())
        except KeyError:
            pass

        # Get object-specific actions
        prefix = f"{object_name}/"
        for key in self.registry_manager.actions.items.keys():
            if key.startswith(prefix):
                action_name = key[len(prefix) :]
                actions.add(action_name)

        # Get generic actions
        for key in self.registry_manager.actions.items.keys():
            if key.startswith("generic/"):
                action_name = key[len("generic/") :]
                actions.add(action_name)

        return sorted(actions)

    def list_all(self) -> List[str]:
        """
        List all registered action keys.

        Returns:
            List of action keys (format: "type/name")
        """
        return list(self.registry_manager.actions.items.keys())


__all__ = ["ActionRepository"]
