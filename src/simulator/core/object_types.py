"""
Object Type Definitions

This module defines ObjectType, which represents the schema for a type of object
in the simulation. It aggregates attributes and provides methods for creating
default instances.

Key concepts:
- Object types are versioned schemas defining what attributes an object has
- Each object type can create default states for simulation
- Validation ensures all object types have at least one attribute
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Dict, TYPE_CHECKING
from simulator.core.attributes import AttributeType

if TYPE_CHECKING:
    from simulator.core.state import ObjectState


class ObjectType(BaseModel):
    """
    Schema definition for a type of object in the simulation.
    
    ObjectType defines what attributes an object has, their value spaces,
    and how to create default instances. It serves as the template from
    which ObjectState instances are created.
    
    Attributes:
        name: Unique identifier for this object type
        version: Schema version number (increment for breaking changes)
        attributes: Dictionary mapping attribute names to their definitions
        
    Examples:
        >>> from simulator.core.quantity import QuantitySpace
        >>> from simulator.core.attributes import AttributeType
        >>> 
        >>> # Define attribute types
        >>> switch_space = QuantitySpace(name="switch", levels=["off", "on"])
        >>> switch_attr = AttributeType(name="switch", space=switch_space, default="off")
        >>> 
        >>> battery_space = QuantitySpace(name="battery", levels=["empty", "low", "med", "high"])
        >>> battery_attr = AttributeType(name="battery_level", space=battery_space, default="med")
        >>> 
        >>> # Create object type
        >>> flashlight = ObjectType(
        ...     name="flashlight",
        ...     version=1,
        ...     attributes={
        ...         "switch": switch_attr,
        ...         "battery_level": battery_attr
        ...     }
        ... )
    """
    name: str
    version: int
    attributes: Dict[str, AttributeType]

    @field_validator("attributes")
    @classmethod
    def _validate_non_empty_attributes(cls, v: Dict[str, AttributeType]) -> Dict[str, AttributeType]:
        """
        Ensure that object types have at least one attribute.
        
        Args:
            v: Dictionary of attributes to validate
            
        Returns:
            The validated attributes dictionary
            
        Raises:
            ValueError: If attributes dictionary is empty
        """
        if not v:
            raise ValueError("ObjectType.attributes cannot be empty - objects must have at least one attribute")
        return v

    def default_state(self) -> "ObjectState":
        """
        Create a default state instance for this object type.
        
        Uses each attribute's effective default value (explicit default if set,
        otherwise the first value in the attribute's quantity space).
        
        Returns:
            ObjectState with all attributes set to their default values
            
        Examples:
            >>> flashlight_type = ObjectType(...)  # Assume defined above
            >>> default_state = flashlight_type.default_state()
            >>> print(default_state.values)
            {'switch': 'off', 'battery_level': 'med'}
        """
        values = {}
        for attr_name, attr in self.attributes.items():
            values[attr_name] = attr.get_effective_default()
        # Import here to avoid circular dependency
        from simulator.core.state import ObjectState
        return ObjectState(object_type=self, values=values)

    def has_attribute(self, attr_name: str) -> bool:
        """
        Check if this object type has a specific attribute.
        
        Args:
            attr_name: Name of the attribute to check
            
        Returns:
            True if the attribute exists, False otherwise
        """
        return attr_name in self.attributes

    def get_attribute(self, attr_name: str) -> AttributeType:
        """
        Get an attribute definition by name.
        
        Args:
            attr_name: Name of the attribute to retrieve
            
        Returns:
            The AttributeType for the specified attribute
            
        Raises:
            KeyError: If the attribute doesn't exist
        """
        if attr_name not in self.attributes:
            raise KeyError(f"Attribute '{attr_name}' not found in object type '{self.name}'")
        return self.attributes[attr_name]

    def validate_state_values(self, values: Dict[str, str]) -> None:
        """
        Validate that a set of attribute values is compatible with this object type.
        
        Args:
            values: Dictionary mapping attribute names to values
            
        Raises:
            ValueError: If any attribute is missing, unknown, or has invalid values
        """
        # Check for missing required attributes
        missing_attrs = set(self.attributes.keys()) - set(values.keys())
        if missing_attrs:
            raise ValueError(f"Missing required attributes: {sorted(missing_attrs)}")
        
        # Check for unknown attributes
        unknown_attrs = set(values.keys()) - set(self.attributes.keys())
        if unknown_attrs:
            raise ValueError(f"Unknown attributes for {self.name}: {sorted(unknown_attrs)}")
        
        # Validate each attribute value
        for attr_name, value in values.items():
            self.attributes[attr_name].validate_value(value)

    def get_identifier(self) -> str:
        """
        Get a unique identifier string for this object type.
        
        Returns:
            String in format "name@vN" (e.g., "flashlight@v1")
        """
        return f"{self.name}@v{self.version}"

    def __str__(self) -> str:
        """Human-readable string representation."""
        attr_count = len(self.attributes)
        attr_names = ", ".join(self.attributes.keys())
        return f"ObjectType({self.get_identifier()}: {attr_count} attributes [{attr_names}])"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"ObjectType(name='{self.name}', version={self.version}, "
            f"attributes={list(self.attributes.keys())})"
        )
