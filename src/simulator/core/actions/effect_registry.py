"""Effect Registry: Extensible registration system for effect types."""

from __future__ import annotations

from typing import Any, Callable, Type

from .effects.base import Effect
from .type_registry import TypeRegistry


class EffectRegistry(TypeRegistry[Effect]):
    """Registry for effect type parsers and builders."""

    _type_name: str = "effect"

    def build_effect(self, spec: Any) -> Effect:
        """Build a runtime Effect object from a spec (alias for build)."""
        return self.build(spec)


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
