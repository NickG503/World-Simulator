"""Effect Registry: Extensible registration system for effect types."""

from __future__ import annotations

from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

from .effects.base import Effect


class EffectRegistry(BaseModel):
    """Registry for effect type parsers and builders."""

    _spec_map: Dict[str, Type[Any]] = {}
    _builder_map: Dict[str, Callable[[Any], Effect]] = {}

    model_config = {"arbitrary_types_allowed": True}

    def register(
        self,
        type_name: str,
        spec_class: Type[Any],
        builder_func: Callable[[Any], Effect],
    ) -> None:
        """
        Register a new effect type.

        Args:
            type_name: The "type" value in YAML (e.g., "set_attribute")
            spec_class: Pydantic model for parsing YAML
            builder_func: Function to build runtime Effect from spec
        """
        self._spec_map[type_name] = spec_class
        # Map by spec class name for the builder lookup
        self._builder_map[spec_class.__name__] = builder_func

    def parse_spec(self, data: Dict[str, Any]) -> Any:
        """
        Parse YAML data into an effect spec.

        Args:
            data: Dict with 'type' field and effect-specific fields

        Returns:
            Pydantic spec model instance

        Raises:
            ValueError: If effect type is unknown
        """
        etype = data.get("type")
        if not etype:
            raise ValueError("Effect spec must have a 'type' field")

        spec_class = self._spec_map.get(etype)
        if not spec_class:
            known = list(self._spec_map.keys())
            raise ValueError(f"Unknown effect type: {etype} (known: {known})")

        return spec_class.model_validate(data)

    def build_effect(self, spec: Any) -> Effect:
        """
        Build a runtime Effect object from a spec.

        Args:
            spec: Effect spec instance

        Returns:
            Runtime Effect object

        Raises:
            TypeError: If no builder registered for spec type
        """
        spec_type_name = type(spec).__name__
        builder = self._builder_map.get(spec_type_name)

        if not builder:
            raise TypeError(f"No builder registered for spec type: {spec_type_name}")

        return builder(spec)

    def list_registered_types(self) -> list[str]:
        """Return list of all registered effect type names."""
        return list(self._spec_map.keys())


# Global singleton instance
_global_effect_registry = EffectRegistry()


def get_effect_registry() -> EffectRegistry:
    """Get the global effect registry instance."""
    return _global_effect_registry


def register_effect(
    type_name: str,
    spec_class: Type[Any],
    builder_func: Callable[[Any], Effect],
) -> None:
    """
    Convenience function to register an effect type on the global registry.

    Args:
        type_name: The "type" value in YAML
        spec_class: Pydantic model for parsing YAML
        builder_func: Function to build runtime Effect from spec
    """
    _global_effect_registry.register(type_name, spec_class, builder_func)


__all__ = [
    "EffectRegistry",
    "get_effect_registry",
    "register_effect",
]
