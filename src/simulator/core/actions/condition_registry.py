"""Condition Registry: Extensible registration system for condition types."""

from __future__ import annotations

from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

from .conditions.base import Condition


class ConditionRegistry(BaseModel):
    """Registry for condition type parsers and builders."""

    _spec_map: Dict[str, Type[Any]] = {}
    _builder_map: Dict[str, Callable[[Any], Condition]] = {}

    model_config = {"arbitrary_types_allowed": True}

    def register(
        self,
        type_name: str,
        spec_class: Type[Any],
        builder_func: Callable[[Any], Condition],
    ) -> None:
        """
        Register a new condition type.

        Args:
            type_name: The "type" value in YAML (e.g., "attribute_check")
            spec_class: Pydantic model for parsing YAML
            builder_func: Function to build runtime Condition from spec
        """
        self._spec_map[type_name] = spec_class
        # Map by spec class name for the builder lookup
        self._builder_map[spec_class.__name__] = builder_func

    def parse_spec(self, data: Dict[str, Any]) -> Any:
        """
        Parse YAML data into a condition spec.

        Args:
            data: Dict with 'type' field and condition-specific fields

        Returns:
            Pydantic spec model instance

        Raises:
            ValueError: If condition type is unknown
        """
        ctype = data.get("type")
        if not ctype:
            raise ValueError("Condition spec must have a 'type' field")

        spec_class = self._spec_map.get(ctype)
        if not spec_class:
            known = list(self._spec_map.keys())
            raise ValueError(f"Unknown condition type: {ctype} (known: {known})")

        return spec_class.model_validate(data)

    def build_condition(self, spec: Any) -> Condition:
        """
        Build a runtime Condition object from a spec.

        Args:
            spec: Condition spec instance

        Returns:
            Runtime Condition object

        Raises:
            TypeError: If no builder registered for spec type
        """
        spec_type_name = type(spec).__name__
        builder = self._builder_map.get(spec_type_name)

        if not builder:
            raise TypeError(f"No builder registered for spec type: {spec_type_name}")

        return builder(spec)

    def list_registered_types(self) -> list[str]:
        """Return list of all registered condition type names."""
        return list(self._spec_map.keys())


# Global singleton instance
_global_condition_registry = ConditionRegistry()


def get_condition_registry() -> ConditionRegistry:
    """Get the global condition registry instance."""
    return _global_condition_registry


def register_condition(
    type_name: str,
    spec_class: Type[Any],
    builder_func: Callable[[Any], Condition],
) -> None:
    """
    Convenience function to register a condition type on the global registry.

    Args:
        type_name: The "type" value in YAML
        spec_class: Pydantic model for parsing YAML
        builder_func: Function to build runtime Condition from spec
    """
    _global_condition_registry.register(type_name, spec_class, builder_func)


__all__ = [
    "ConditionRegistry",
    "get_condition_registry",
    "register_condition",
]
