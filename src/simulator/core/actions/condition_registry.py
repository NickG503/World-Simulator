"""Condition Registry: Extensible registration system for condition types."""

from __future__ import annotations

from typing import Any, Callable, Type

from .conditions.base import Condition
from .type_registry import TypeRegistry


class ConditionRegistry(TypeRegistry[Condition]):
    """Registry for condition type parsers and builders."""

    _type_name: str = "condition"

    def build_condition(self, spec: Any) -> Condition:
        """Build a runtime Condition object from a spec (alias for build)."""
        return self.build(spec)


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
# todo : add something about the registry in the readme
