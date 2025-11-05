"""Validation Service: Validates knowledge base consistency and references."""

from __future__ import annotations

from typing import List

from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.repositories.action_repository import ActionRepository
from simulator.repositories.object_repository import ObjectRepository
from simulator.repositories.space_repository import SpaceRepository


class ValidationService:
    """
    Service for validating knowledge base consistency.

    Coordinates validation across registries, objects, actions, and spaces.
    """

    def __init__(
        self,
        registry_manager: RegistryManager,
        object_repository: ObjectRepository,
        action_repository: ActionRepository,
        space_repository: SpaceRepository,
    ):
        """
        Initialize validation service.

        Args:
            registry_manager: Registry manager for validation
            object_repository: Object repository
            action_repository: Action repository
            space_repository: Space repository
        """
        self.registry_manager = registry_manager
        self.object_repo = object_repository
        self.action_repo = action_repository
        self.space_repo = space_repository
        self.validator = RegistryValidator(registry_manager)

    def validate_all(self) -> List[str]:
        """
        Validate entire knowledge base.

        Returns:
            List of validation error messages (empty if valid)
        """
        return self.validator.validate_all()

    def validate_object(self, object_name: str) -> List[str]:
        """
        Validate a specific object type.

        Args:
            object_name: Object type name

        Returns:
            List of validation error messages
        """
        errors = []

        # Check if object exists
        if not self.object_repo.exists(object_name):
            errors.append(f"Object '{object_name}' not found")
            return errors

        # Get object and validate its references
        obj_type = self.object_repo.get_by_name(object_name)

        # Validate space references
        for part_name, part_spec in obj_type.parts.items():
            for attr_name, attr_spec in part_spec.attributes.items():
                if not self.space_repo.exists(attr_spec.space_id):
                    errors.append(
                        f"Object '{object_name}' part '{part_name}' "
                        f"attribute '{attr_name}' references unknown space '{attr_spec.space_id}'"
                    )

        # Validate global attributes
        for attr_name, attr_spec in obj_type.global_attributes.items():
            if not self.space_repo.exists(attr_spec.space_id):
                errors.append(
                    f"Object '{object_name}' global attribute '{attr_name}' "
                    f"references unknown space '{attr_spec.space_id}'"
                )

        return errors

    def validate_action(self, object_name: str, action_name: str) -> List[str]:
        """
        Validate a specific action for an object.

        Args:
            object_name: Object type name
            action_name: Action name

        Returns:
            List of validation error messages
        """
        errors = []

        # Check if action exists
        action = self.action_repo.find_for_object(object_name, action_name)
        if not action:
            errors.append(f"Action '{action_name}' not found for object '{object_name}'")
            return errors

        # Additional validation could be added here:
        # - Parameter validation
        # - Precondition/effect attribute references
        # - etc.

        return errors

    def get_validation_summary(self) -> dict:
        """
        Get a summary of the knowledge base validation state.

        Returns:
            Dict with validation statistics
        """
        all_errors = self.validate_all()

        return {
            "valid": len(all_errors) == 0,
            "error_count": len(all_errors),
            "errors": all_errors,
            "object_count": len(self.object_repo.list_all()),
            "action_count": len(self.action_repo.list_all()),
            "space_count": len(self.space_repo.list_all()),
        }


__all__ = ["ValidationService"]
