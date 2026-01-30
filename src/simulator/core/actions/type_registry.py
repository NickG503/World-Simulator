"""TypeRegistry: Generic base class for extensible type registration systems."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T")  # The runtime type (e.g., Condition, Effect)


class TypeRegistry(BaseModel, Generic[T]):
    """Generic registry for type parsers and builders.

    This base class provides a reusable pattern for registering spec classes
    and builder functions that convert specs into runtime objects.

    Type Parameters:
        T: The runtime type that builders create (e.g., Condition, Effect)
    """

    _spec_map: Dict[str, Type[Any]] = {}
    _builder_map: Dict[str, Callable[[Any], T]] = {}
    _type_name: str = "item"  # For error messages

    model_config = {"arbitrary_types_allowed": True}

    def register(
        self,
        type_name: str,
        spec_class: Type[Any],
        builder_func: Callable[[Any], T],
    ) -> None:
        """Register a new type.

        Args:
            type_name: The "type" value in YAML (e.g., "attribute_check")
            spec_class: Pydantic model for parsing YAML
            builder_func: Function to build runtime object from spec
        """
        self._spec_map[type_name] = spec_class
        self._builder_map[spec_class.__name__] = builder_func

    def parse_spec(self, data: Dict[str, Any]) -> Any:
        """Parse YAML data into a spec.

        Args:
            data: Dict with 'type' field and type-specific fields

        Returns:
            Pydantic spec model instance

        Raises:
            ValueError: If type is unknown
        """
        type_value = data.get("type")
        if not type_value:
            raise ValueError(f"{self._type_name.capitalize()} spec must have a 'type' field")

        spec_class = self._spec_map.get(type_value)
        if not spec_class:
            known = list(self._spec_map.keys())
            raise ValueError(f"Unknown {self._type_name} type: {type_value} (known: {known})")

        return spec_class.model_validate(data)

    def build(self, spec: Any) -> T:
        """Build a runtime object from a spec.

        Args:
            spec: Spec instance

        Returns:
            Runtime object

        Raises:
            TypeError: If no builder registered for spec type
        """
        spec_type_name = type(spec).__name__
        builder = self._builder_map.get(spec_type_name)

        if not builder:
            raise TypeError(f"No builder registered for spec type: {spec_type_name}")

        return builder(spec)

    def list_registered_types(self) -> list[str]:
        """Return list of all registered type names."""
        return list(self._spec_map.keys())


__all__ = ["TypeRegistry"]
