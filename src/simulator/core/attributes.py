"""
Object Attribute Definitions

This module defines AttributeType, which combines a QuantitySpace with
metadata like mutability and default values to fully specify an object attribute.

Key concepts:
- Attributes have a defined qualitative value space
- Mutability controls whether actions can modify the attribute
- Default values provide sensible starting states
"""

from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional
from simulator.core.quantity import QuantitySpace


class AttributeType(BaseModel):
    """
    Definition of an object attribute with its value space and properties.
    
    AttributeType combines a QuantitySpace with metadata to fully specify
    how an attribute behaves in the simulation. This includes what values
    are valid, whether it can be changed, and what its default value should be.
    
    Attributes:
        name: Human-readable name for this attribute
        space: QuantitySpace defining valid values and their ordering
        mutable: Whether actions can modify this attribute's value
        default: Default value when creating new object instances
        
    Examples:
        >>> from simulator.core.quantity import QuantitySpace
        >>> battery_space = QuantitySpace(name="battery", levels=["empty", "low", "med", "high"])
        >>> battery_attr = AttributeType(
        ...     name="battery_level",
        ...     space=battery_space,
        ...     mutable=True,
        ...     default="med"
        ... )
    """
    name: str
    space: QuantitySpace
    mutable: bool = True
    default: Optional[str] = None

    @field_validator("default")
    @classmethod
    def _validate_default_in_space(cls, v: Optional[str], info) -> Optional[str]:
        """
        Ensure the default value is valid within the attribute's quantity space.
        
        Args:
            v: The default value to validate
            info: Pydantic validation context containing other field values
            
        Returns:
            The validated default value
            
        Raises:
            ValueError: If default is not None and not in the quantity space
        """
        if v is None:
            return v
            
        space = info.data.get("space")
        if space and not space.has(v):
            raise ValueError(
                f"default value {v!r} not in quantity space {space.levels!r} "
                f"for attribute space '{space.name}'"
            )
        return v

    def get_effective_default(self) -> str:
        """
        Get the effective default value for this attribute.
        
        If an explicit default is set, returns that. Otherwise returns
        the first (lowest) value in the quantity space.
        
        Returns:
            The default value to use when creating new object states
        """
        if self.default is not None:
            return self.default
        return self.space.levels[0]

    def validate_value(self, value: str) -> None:
        """
        Validate that a value is acceptable for this attribute.
        
        Args:
            value: The value to validate
            
        Raises:
            ValueError: If the value is not in this attribute's quantity space
        """
        if not self.space.has(value):
            raise ValueError(
                f"Value {value!r} is not valid for attribute '{self.name}'. "
                f"Must be one of: {self.space.levels}"
            )

    def can_modify(self) -> bool:
        """
        Check if this attribute can be modified by actions.
        
        Returns:
            True if the attribute is mutable, False otherwise
        """
        return self.mutable

    def __str__(self) -> str:
        """Human-readable string representation."""
        mutability = "mutable" if self.mutable else "immutable"
        default_info = f", default={self.default}" if self.default else ""
        return f"AttributeType({self.name}: {self.space.name} [{mutability}{default_info}])"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"AttributeType(name='{self.name}', space={self.space!r}, "
            f"mutable={self.mutable}, default={self.default!r})"
        )