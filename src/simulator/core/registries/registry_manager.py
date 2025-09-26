from __future__ import annotations
from pydantic import BaseModel, Field
from simulator.core.attributes import QualitativeSpace, QualitativeSpaceRegistry, AttributeRegistry
from simulator.core.objects.object_type import ObjectType, ObjectBehavior
from simulator.core.actions.action import Action
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

    model_config = {"arbitrary_types_allowed": True}

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
        # Brightness level
        if "brightness_level" not in self.spaces.spaces:
            self.spaces.register(
                QualitativeSpace(id="brightness_level", name="Brightness Level", levels=["none", "low", "medium", "high"])  # type: ignore[arg-type]
            )
        # Temperature level
        if "temperature_level" not in self.spaces.spaces:
            self.spaces.register(
                QualitativeSpace(id="temperature_level", name="Temperature Level", levels=["cold", "warm", "hot", "very_hot"])  # type: ignore[arg-type]
            )
        # Water level
        if "water_level" not in self.spaces.spaces:
            self.spaces.register(
                QualitativeSpace(id="water_level", name="Water Level", levels=["empty", "low", "medium", "high", "full"])  # type: ignore[arg-type]
            )

    def find_action_for_object(self, object_name: str, action_name: str):
        """Find action for object - simple behavior-based approach."""
        # 1. Check if object has custom behavior for this action
        obj_type = self.objects.get(object_name)
        if action_name in obj_type.behaviors:
            # Look for generic action as template
            generic_key = f"generic/{action_name}"
            if generic_key in self.actions.items:
                return self.actions.get(generic_key)
        
        # 2. Direct object-specific action (legacy support)
        specific_key = f"{object_name}/{action_name}"
        if specific_key in self.actions.items:
            return self.actions.get(specific_key)
        
        # 3. Generic action without behavior
        generic_key = f"generic/{action_name}"
        if generic_key in self.actions.items:
            return self.actions.get(generic_key)
            
        return None

    def create_behavior_enhanced_action(self, object_name: str, action_name: str):
        """Create an action enhanced with object-specific behavior if available."""
        base_action = self.find_action_for_object(object_name, action_name)
        if not base_action:
            return None
        
        # Check if object has custom behavior for this action
        obj_type = self.objects.get(object_name)
        if action_name in obj_type.behaviors:
            # Merge behavior into action
            behavior = obj_type.behaviors[action_name]
            enhanced_action = self._merge_action_with_behavior(base_action, behavior)
            return enhanced_action
        
        return base_action
    
    def _merge_action_with_behavior(self, base_action: Action, behavior: ObjectBehavior):
        """Merge object behavior with base action."""
        # Import here to avoid circular imports
        from simulator.core.actions.action import Action
        # Behavior preconditions/effects are already parsed at load time
        behavior_preconditions = behavior.preconditions
        behavior_effects = behavior.effects
        
        # Create new action combining base + behavior  
        # Priority: behavior preconditions/effects override base ones
        merged_preconditions = behavior_preconditions if behavior_preconditions else base_action.preconditions
        merged_effects = behavior_effects if behavior_effects else base_action.effects
        
        return Action(
            name=base_action.name,
            object_type=base_action.object_type,
            parameters=base_action.parameters,
            preconditions=merged_preconditions,
            effects=merged_effects,
            metadata=base_action.metadata
        )

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
