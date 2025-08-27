"""
Object State Management

This module defines ObjectState, which represents the current state of an object
instance in the simulation. It includes both attribute values and trend metadata.

Key concepts:
- Object states are validated instances of object types
- Values must be within each attribute's defined quantity space
- Trends track directional changes for qualitative reasoning
- States are immutable except through controlled modification methods
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Dict, Literal, Optional, TYPE_CHECKING, Any
import copy

if TYPE_CHECKING:
    from simulator.core.object_types import ObjectType

# Type alias for trend directions
Trend = Literal["up", "down", "none"]


class ObjectState(BaseModel):
    """
    Current state of an object instance in the simulation.
    
    ObjectState represents a validated snapshot of an object's attribute values
    and trends at a specific point in time. It ensures all values are within
    their defined quantity spaces and provides methods for safe modification.
    
    Attributes:
        object_type: The ObjectType schema this state conforms to
        values: Current values for each attribute (must be in attribute's space)
        trends: Directional metadata for each attribute (up/down/none)
        
    Examples:
        >>> # Assuming flashlight_type is defined
        >>> state = ObjectState(
        ...     object_type=flashlight_type,
        ...     values={"switch": "off", "battery_level": "med"},
        ...     trends={"battery_level": "none"}
        ... )
        >>> state.get_value("switch")
        'off'
        >>> state.set_value("switch", "on")  # If switch is mutable
    """
    object_type: Any  # ObjectType - using Any to avoid circular import issues
    values: Dict[str, str]
    trends: Dict[str, Trend] = {}
    
    model_config = {"arbitrary_types_allowed": True}

    @field_validator("values")
    @classmethod
    def _validate_values_against_schema(cls, v: Dict[str, str], info) -> Dict[str, str]:
        """
        Validate that all attribute values conform to the object type schema.
        
        Ensures:
        1. All required attributes are present
        2. No unknown attributes are included
        3. All values are within their attribute's quantity space
        
        Args:
            v: Dictionary of attribute values to validate
            info: Pydantic validation context containing object_type
            
        Returns:
            The validated values dictionary
            
        Raises:
            ValueError: If validation fails for any reason
        """
        obj_type = info.data.get("object_type")
        if obj_type is None:
            # During construction, object_type might not be set yet
            return v
            
        # Ensure all required attributes are present
        for attr_name, attr in obj_type.attributes.items():
            if attr_name not in v:
                raise ValueError(f"Missing value for required attribute '{attr_name}'")
            
            # Validate value is in attribute's quantity space
            if not attr.space.has(v[attr_name]):
                raise ValueError(
                    f"Attribute '{attr_name}' has invalid value {v[attr_name]!r}. "
                    f"Must be one of: {attr.space.levels}"
                )
        
        # Check for unknown attributes
        for attr_name in v.keys():
            if attr_name not in obj_type.attributes:
                raise ValueError(
                    f"Unknown attribute '{attr_name}' for object type '{obj_type.name}'. "
                    f"Valid attributes: {list(obj_type.attributes.keys())}"
                )
        
        return v

    def get_value(self, attr_name: str) -> str:
        """
        Get the current value of an attribute.
        
        Args:
            attr_name: Name of the attribute to retrieve
            
        Returns:
            Current value of the attribute
            
        Raises:
            KeyError: If the attribute doesn't exist
        """
        if attr_name not in self.values:
            raise KeyError(f"Attribute '{attr_name}' not found in state")
        return self.values[attr_name]

    def get_trend(self, attr_name: str) -> Trend:
        """
        Get the current trend for an attribute.
        
        Args:
            attr_name: Name of the attribute
            
        Returns:
            Current trend ("up", "down", or "none")
        """
        return self.trends.get(attr_name, "none")

    def set_value(self, attr_name: str, new_value: str) -> None:
        """
        Set a new value for an attribute with validation.
        
        This method provides controlled modification of attribute values,
        ensuring mutability constraints and value space constraints are respected.
        
        Args:
            attr_name: Name of the attribute to modify
            new_value: New value to set (must be in attribute's space)
            
        Raises:
            KeyError: If the attribute doesn't exist
            ValueError: If the attribute is immutable or value is invalid
        """
        if attr_name not in self.object_type.attributes:
            raise KeyError(f"Attribute '{attr_name}' not found in object type '{self.object_type.name}'")
        
        attr = self.object_type.attributes[attr_name]
        
        # Check mutability
        if not attr.mutable:
            raise ValueError(f"Attribute '{attr_name}' is immutable and cannot be modified")
        
        # Validate new value is in quantity space
        if not attr.space.has(new_value):
            raise ValueError(
                f"Value {new_value!r} not valid for attribute '{attr_name}'. "
                f"Must be one of: {attr.space.levels}"
            )
        
        self.values[attr_name] = new_value

    def set_trend(self, attr_name: str, trend: Trend) -> None:
        """
        Set the trend for an attribute.
        
        Args:
            attr_name: Name of the attribute
            trend: New trend direction ("up", "down", or "none")
            
        Raises:
            KeyError: If the attribute doesn't exist
        """
        if attr_name not in self.object_type.attributes:
            raise KeyError(f"Attribute '{attr_name}' not found in object type '{self.object_type.name}'")
        
        self.trends[attr_name] = trend

    def copy(self) -> 'ObjectState':
        """
        Create a deep copy of this state.
        
        Returns:
            New ObjectState instance with identical values and trends
        """
        return ObjectState(
            object_type=self.object_type,
            values=copy.deepcopy(self.values),
            trends=copy.deepcopy(self.trends)
        )

    def get_all_attributes(self) -> Dict[str, str]:
        """
        Get a copy of all attribute values.
        
        Returns:
            Dictionary mapping attribute names to their current values
        """
        return self.values.copy()

    def get_all_trends(self) -> Dict[str, Trend]:
        """
        Get a copy of all attribute trends.
        
        Returns:
            Dictionary mapping attribute names to their current trends
        """
        return self.trends.copy()

    def has_attribute(self, attr_name: str) -> bool:
        """
        Check if this state has a specific attribute.
        
        Args:
            attr_name: Name of the attribute to check
            
        Returns:
            True if the attribute exists, False otherwise
        """
        return attr_name in self.values

    def __str__(self) -> str:
        """Human-readable string representation."""
        type_id = self.object_type.get_identifier()
        value_summary = ", ".join(f"{k}={v}" for k, v in self.values.items())
        return f"ObjectState({type_id}: {value_summary})"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"ObjectState(object_type={self.object_type.get_identifier()!r}, "
            f"values={self.values!r}, trends={self.trends!r})"
        )