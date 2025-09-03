"""Capability system for generic actions."""

from __future__ import annotations
from typing import Dict, List, Set
from pydantic import BaseModel, Field
from simulator.core.objects import ObjectType, AttributeTarget


class CapabilityRequirement(BaseModel):
    """Defines what attributes/parts an object needs to support a capability."""
    
    name: str
    description: str
    required_attributes: List[AttributeTarget]  # Must have these attributes
    required_spaces: Dict[str, str]  # attribute_name -> space_id mapping


class CapabilityDetector:
    """Detects what capabilities an object supports based on its structure."""
    
    def __init__(self):
        self.capability_requirements = {
            "switchable": CapabilityRequirement(
                name="switchable",
                description="Can be turned on/off via a switch",
                required_attributes=[
                    AttributeTarget.from_string("switch.position"),
                ],
                required_spaces={
                    "switch.position": "binary_state"
                }
            ),
            "illuminating": CapabilityRequirement(
                name="illuminating",
                description="Can produce light with controllable state",
                required_attributes=[
                    AttributeTarget.from_string("bulb.state"),
                ],
                required_spaces={
                    "bulb.state": "binary_state"
                }
            ),
            "battery_powered": CapabilityRequirement(
                name="battery_powered",
                description="Has a battery with level tracking",
                required_attributes=[
                    AttributeTarget.from_string("battery.level"),
                ],
                required_spaces={
                    "battery.level": "battery_level"
                }
            ),
            "fillable": CapabilityRequirement(
                name="fillable",
                description="Can hold liquid with level tracking",
                required_attributes=[
                    AttributeTarget.from_string("container.contents_level"),
                ],
                required_spaces={
                    "container.contents_level": "liquid_amount"
                }
            ),
            "heatable": CapabilityRequirement(
                name="heatable",
                description="Can be heated with temperature control",
                required_attributes=[
                    AttributeTarget.from_string("heater.temperature"),
                ],
                required_spaces={
                    "heater.temperature": "temperature_level"
                }
            ),
            "water_container": CapabilityRequirement(
                name="water_container",
                description="Can hold water with level tracking",
                required_attributes=[
                    AttributeTarget.from_string("tank.level"),
                ],
                required_spaces={
                    "tank.level": "water_level"
                }
            )
        }
    
    def detect_capabilities(self, obj_type: ObjectType) -> Set[str]:
        """Detect what capabilities this object type supports."""
        capabilities = set()
        
        for cap_name, requirement in self.capability_requirements.items():
            if self._supports_capability(obj_type, requirement):
                capabilities.add(cap_name)
        
        return capabilities
    
    def _supports_capability(self, obj_type: ObjectType, requirement: CapabilityRequirement) -> bool:
        """Check if object supports a specific capability."""
        for attr_target in requirement.required_attributes:
            if not self._has_attribute(obj_type, attr_target):
                return False
            
            # Check if attribute uses correct space
            attr_key = attr_target.to_string()
            if attr_key in requirement.required_spaces:
                expected_space = requirement.required_spaces[attr_key]
                actual_space = self._get_attribute_space(obj_type, attr_target)
                if actual_space != expected_space:
                    return False
        
        return True
    
    def _has_attribute(self, obj_type: ObjectType, target: AttributeTarget) -> bool:
        """Check if object has the specified attribute."""
        if target.part is None:
            return target.attribute in obj_type.global_attributes
        
        if target.part not in obj_type.parts:
            return False
        
        return target.attribute in obj_type.parts[target.part].attributes
    
    def _get_attribute_space(self, obj_type: ObjectType, target: AttributeTarget) -> str:
        """Get the space_id for an attribute."""
        if target.part is None:
            return obj_type.global_attributes[target.attribute].space_id
        
        return obj_type.parts[target.part].attributes[target.attribute].space_id


class CapabilityRegistry(BaseModel):
    """Registry of object capabilities."""

    object_capabilities: Dict[str, Set[str]] = Field(default_factory=dict)  # object_name -> set of capabilities
    
    def register_object_capabilities(self, object_name: str, capabilities: Set[str]):
        """Register capabilities for an object type."""
        self.object_capabilities[object_name] = capabilities
    
    def get_capabilities(self, object_name: str) -> Set[str]:
        """Get capabilities for an object type."""
        return self.object_capabilities.get(object_name, set())
    
    def find_objects_with_capability(self, capability: str) -> List[str]:
        """Find all objects that support a specific capability."""
        return [
            obj_name for obj_name, caps in self.object_capabilities.items()
            if capability in caps
        ]
