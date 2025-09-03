from __future__ import annotations
from pydantic import BaseModel, Field
from simulator.core.attributes import QualitativeSpace, QualitativeSpaceRegistry, AttributeRegistry
from simulator.core.objects.object_type import ObjectType
from simulator.core.capabilities import CapabilityRegistry, CapabilityDetector
from .registry_base import NameRegistry


class ObjectTypeRegistry(NameRegistry[ObjectType]):
    pass


class ActionRegistry(NameRegistry[object]):
    pass


class RegistryManager(BaseModel):
    """Central manager for all registries."""

    spaces: QualitativeSpaceRegistry = Field(default_factory=QualitativeSpaceRegistry)
    attributes: AttributeRegistry = Field(default_factory=AttributeRegistry)
    objects: ObjectTypeRegistry = Field(default_factory=ObjectTypeRegistry)
    actions: ActionRegistry = Field(default_factory=ActionRegistry)
    capabilities: CapabilityRegistry = Field(default_factory=CapabilityRegistry)

    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self, **data):
        super().__init__(**data)
        self._capability_detector = CapabilityDetector()

    def register_defaults(self) -> None:
        """Register common qualitative spaces."""
        # Binary state
        if "binary_state" not in self.spaces.spaces:
            self.spaces.register(
                QualitativeSpace(id="binary_state", name="Binary State", levels=["off", "on"])  # type: ignore[arg-type]
            )
        # Battery level
        if "battery_level" not in self.spaces.spaces:
            self.spaces.register(
                QualitativeSpace(id="battery_level", name="Battery Level", levels=["empty", "low", "medium", "high", "full"])  # type: ignore[arg-type]
            )

    def detect_and_register_capabilities(self) -> None:
        """Detect capabilities for all registered objects."""
        for obj_name, obj_type in self.objects.items.items():
            capabilities = self._capability_detector.detect_capabilities(obj_type)
            self.capabilities.register_object_capabilities(obj_name, capabilities)
    
    def find_compatible_actions(self, object_name: str, action_name: str) -> list[str]:
        """Find all actions compatible with an object (capability-based + specific)."""
        compatible = []
        
        # 1. Direct object-specific action
        specific_key = f"{object_name}/{action_name}"
        if specific_key in self.actions.items:
            compatible.append(specific_key)
        
        # 2. Capability-based actions
        obj_capabilities = self.capabilities.get_capabilities(object_name)
        for action_key, action in self.actions.items.items():
            if hasattr(action, 'is_capability_based') and action.is_capability_based():
                if action.required_capabilities.issubset(obj_capabilities):
                    if action.name == action_name:
                        compatible.append(action_key)
        
        return compatible

    def validate_references(self) -> None:
        """Cross-registry validation for Phase 1.

        Validates:
        - All attribute specs reference known qualitative spaces
        - Actions reference valid object parts/attributes and parameters
        """
        # Ensure all attribute specs reference known spaces
        for spec in self.attributes.attributes.values():
            _ = self.spaces.get(spec.space_id)

        # Run structured validator over objects/actions
        from .validators import RegistryValidator  # local import to avoid cycles
        errors = RegistryValidator(self).validate_all()
        if errors:
            msg = "Registry validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise RuntimeError(msg)
