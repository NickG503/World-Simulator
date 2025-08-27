"""
Object Type Registry

This module provides a centralized registry for managing object types in memory.
The registry ensures unique registration and provides fast lookup by name and version.

Key concepts:
- Object types are stored by (name, version) tuple for uniqueness
- Duplicate registrations are prevented
- Fast lookup operations for CLI and engine use
"""

from __future__ import annotations
from typing import Dict, Tuple, Iterable, List, Optional
from .object_types import ObjectType


class Registry:
    """
    In-memory registry for object types with version management.
    
    The Registry provides centralized storage and retrieval of ObjectType
    definitions. It ensures uniqueness by (name, version) and provides
    convenient methods for querying available types.
    
    Examples:
        >>> registry = Registry()
        >>> registry.add_object_type(flashlight_type)
        >>> registry.add_object_type(kettle_type)
        >>> 
        >>> # Retrieve specific version
        >>> flashlight = registry.get("flashlight", 1)
        >>> 
        >>> # List all types
        >>> all_types = list(registry.all())
    """
    
    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._types: Dict[Tuple[str, int], ObjectType] = {}

    def add_object_type(self, obj_type: ObjectType) -> None:
        """
        Register a new object type in the registry.
        
        Args:
            obj_type: The ObjectType to register
            
        Raises:
            ValueError: If an object type with the same name and version
                       is already registered
        """
        key = (obj_type.name, obj_type.version)
        if key in self._types:
            raise ValueError(
                f"Duplicate type registration: {obj_type.name}@v{obj_type.version}. "
                f"Object types must have unique (name, version) combinations."
            )
        self._types[key] = obj_type

    def get(self, name: str, version: int) -> ObjectType:
        """
        Retrieve an object type by name and version.
        
        Args:
            name: Name of the object type
            version: Version number of the object type
            
        Returns:
            The ObjectType matching the specified name and version
            
        Raises:
            KeyError: If no object type matches the name and version
        """
        key = (name, version)
        if key not in self._types:
            available = [f"{n}@v{v}" for n, v in self._types.keys()]
            raise KeyError(
                f"Unknown object type {name}@v{version}. "
                f"Available types: {', '.join(sorted(available))}"
            )
        return self._types[key]

    def has(self, name: str, version: int) -> bool:
        """
        Check if an object type exists in the registry.
        
        Args:
            name: Name of the object type
            version: Version number of the object type
            
        Returns:
            True if the object type exists, False otherwise
        """
        return (name, version) in self._types

    def get_latest_version(self, name: str) -> Optional[ObjectType]:
        """
        Get the latest version of an object type by name.
        
        Args:
            name: Name of the object type
            
        Returns:
            The ObjectType with the highest version number for the given name,
            or None if no object type with that name exists
        """
        matching_versions = [
            (version, obj_type) for (type_name, version), obj_type in self._types.items()
            if type_name == name
        ]
        
        if not matching_versions:
            return None
            
        # Return the object type with the highest version number
        latest_version, latest_type = max(matching_versions, key=lambda x: x[0])
        return latest_type

    def get_all_versions(self, name: str) -> List[ObjectType]:
        """
        Get all versions of an object type by name, sorted by version.
        
        Args:
            name: Name of the object type
            
        Returns:
            List of ObjectTypes with the given name, sorted by version (ascending)
        """
        matching_types = [
            (version, obj_type) for (type_name, version), obj_type in self._types.items()
            if type_name == name
        ]
        
        # Sort by version number and return just the object types
        return [obj_type for version, obj_type in sorted(matching_types, key=lambda x: x[0])]

    def get_type_names(self) -> List[str]:
        """
        Get a list of all unique object type names in the registry.
        
        Returns:
            Sorted list of unique object type names
        """
        names = {name for name, version in self._types.keys()}
        return sorted(names)

    def all(self) -> Iterable[ObjectType]:
        """
        Get all registered object types.
        
        Returns:
            Iterator over all ObjectType instances in the registry
        """
        return self._types.values()

    def count(self) -> int:
        """
        Get the total number of registered object types.
        
        Returns:
            Number of object types in the registry
        """
        return len(self._types)

    def clear(self) -> None:
        """
        Remove all object types from the registry.
        
        Warning: This operation cannot be undone.
        """
        self._types.clear()

    def remove(self, name: str, version: int) -> ObjectType:
        """
        Remove an object type from the registry.
        
        Args:
            name: Name of the object type to remove
            version: Version of the object type to remove
            
        Returns:
            The removed ObjectType
            
        Raises:
            KeyError: If the object type doesn't exist
        """
        key = (name, version)
        if key not in self._types:
            raise KeyError(f"Cannot remove unknown object type {name}@v{version}")
        return self._types.pop(key)

    def __len__(self) -> int:
        """Return the number of registered object types."""
        return len(self._types)

    def __contains__(self, key: Tuple[str, int]) -> bool:
        """Check if a (name, version) tuple exists in the registry."""
        return key in self._types

    def __str__(self) -> str:
        """Human-readable string representation."""
        count = len(self._types)
        type_names = self.get_type_names()
        return f"Registry({count} types: {', '.join(type_names)})"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        identifiers = [f"{name}@v{version}" for name, version in sorted(self._types.keys())]
        return f"Registry({identifiers})"