"""Behavior Resolver Service: Finds and merges actions with object behaviors."""

from __future__ import annotations

from typing import Optional

from simulator.core.actions.action import Action
from simulator.repositories.action_repository import ActionRepository
from simulator.repositories.object_repository import ObjectRepository


class BehaviorResolverService:
    """
    Service for resolving actions with object-specific behaviors.

    This service encapsulates the complex logic of determining which action
    to use for a given object, including generic vs object-specific actions
    and behavior overrides.
    """

    def __init__(
        self,
        object_repository: ObjectRepository,
        action_repository: ActionRepository,
    ):
        """
        Initialize behavior resolver service.

        Args:
            object_repository: Repository for object type access
            action_repository: Repository for action access
        """
        self.object_repo = object_repository
        self.action_repo = action_repository

    def resolve_action(
        self,
        object_name: str,
        action_name: str,
        *,
        enhanced: bool = True,
    ) -> Optional[Action]:
        """
        Resolve the appropriate action for an object.

        Args:
            object_name: Object type name
            action_name: Action name
            enhanced: If True, merge with object behavior (default: True)

        Returns:
            Action if found, None otherwise
        """
        if enhanced:
            # Get behavior-enhanced action (generic + object behavior)
            return self.action_repo.get_enhanced_action(object_name, action_name)
        else:
            # Get base action without behavior enhancement
            return self.action_repo.find_for_object(object_name, action_name)

    def list_actions_for_object(self, object_name: str) -> list[str]:
        """
        List all actions available for an object.

        Args:
            object_name: Object type name

        Returns:
            List of action names
        """
        return self.action_repo.list_for_object(object_name)

    def has_custom_behavior(self, object_name: str, action_name: str) -> bool:
        """
        Check if object has a custom behavior for an action.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            True if object has custom behavior
        """
        return self.object_repo.has_behavior(object_name, action_name)

    def get_action_source(self, object_name: str, action_name: str) -> str:
        """
        Determine the source of an action.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            "behavior", "specific", "generic", or "not_found"
        """
        # Check if object has custom behavior
        if self.object_repo.has_behavior(object_name, action_name):
            return "behavior"

        # Check for object-specific action
        if self.action_repo.get_specific(object_name, action_name):
            return "specific"

        # Check for generic action
        if self.action_repo.get_generic(action_name):
            return "generic"

        return "not_found"


__all__ = ["BehaviorResolverService"]
