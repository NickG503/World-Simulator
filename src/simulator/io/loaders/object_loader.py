from __future__ import annotations
import glob
import os
from typing import Any, Dict
import yaml
from simulator.core.attributes import AttributeSpec, AttributeInstance
from simulator.core.objects import PartSpec, PartInstance
from simulator.core.objects.object_type import ObjectType, ObjectConstraint, ObjectBehavior
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager


def _read_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _spec_from_yaml(obj_name: str, data: Dict[str, Any]) -> ObjectType:
    name = str(data["type"]).strip()

    parts_raw = data.get("parts", {}) or {}
    parts: Dict[str, PartSpec] = {}
    for p_name, p_spec in parts_raw.items():
        attrs_raw = p_spec.get("attributes", {}) or {}
        attrs: Dict[str, AttributeSpec] = {}
        for a_name, a_spec in attrs_raw.items():
            spec = AttributeSpec(
                name=a_name,
                space_id=str(a_spec["space"]),
                mutable=bool(a_spec.get("mutable", True)),
                default_value=a_spec.get("default"),
            )
            attrs[a_name] = spec
        parts[p_name] = PartSpec(name=p_name, attributes=attrs)

    globals_raw = data.get("global_attributes", {}) or {}
    global_attrs: Dict[str, AttributeSpec] = {}
    for g_name, g_spec in globals_raw.items():
        spec = AttributeSpec(
            name=g_name,
            space_id=str(g_spec["space"]),
            mutable=bool(g_spec.get("mutable", True)),
            default_value=g_spec.get("default"),
        )
        global_attrs[g_name] = spec

    # constraints (optional)
    constraints_raw = data.get("constraints", []) or []
    constraints = [ObjectConstraint(**c) for c in constraints_raw if isinstance(c, dict)]

    # behaviors (optional)
    behaviors_raw = data.get("behaviors", {}) or {}
    behaviors: Dict[str, ObjectBehavior] = {}
    for behavior_name, behavior_spec in behaviors_raw.items():
        behavior = ObjectBehavior(
            preconditions=behavior_spec.get("preconditions", []),
            effects=behavior_spec.get("effects", [])
        )
        behaviors[behavior_name] = behavior

    return ObjectType(name=name, parts=parts, global_attributes=global_attrs, constraints=constraints, behaviors=behaviors)


def load_object_types(path: str, registries: RegistryManager) -> None:
    if not os.path.exists(path):
        return
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        data = _read_yaml(fp)
        if "type" not in data:
            raise ValueError(f"{fp}: missing 'type'")
        obj_type = _spec_from_yaml(data["type"], data)
        registries.objects.register(obj_type.name, obj_type)


def instantiate_default(obj_type: ObjectType, registries: RegistryManager) -> ObjectInstance:
    parts: Dict[str, PartInstance] = {}
    for p_name, p_spec in obj_type.parts.items():
        attrs: Dict[str, AttributeInstance] = {}
        for a_name, a_spec in p_spec.attributes.items():
            space = registries.spaces.get(a_spec.space_id)
            # Handle 'unknown' as a special default value
            if a_spec.default_value == "unknown":
                default = "unknown"
                confidence = 0.0  # Unknown values have no confidence
            else:
                default = a_spec.default_value if a_spec.default_value is not None else space.levels[0]
                confidence = 1.0
            
            attrs[a_name] = AttributeInstance(
                spec=a_spec, 
                current_value=default, 
                trend="none",
                confidence=confidence
            )
        parts[p_name] = PartInstance(spec=p_spec, attributes=attrs)

    g_attrs: Dict[str, AttributeInstance] = {}
    for g_name, g_spec in obj_type.global_attributes.items():
        space = registries.spaces.get(g_spec.space_id)
        # Handle 'unknown' as a special default value
        if g_spec.default_value == "unknown":
            default = "unknown"
            confidence = 0.0  # Unknown values have no confidence
        else:
            default = g_spec.default_value if g_spec.default_value is not None else space.levels[0]
            confidence = 1.0
            
        g_attrs[g_name] = AttributeInstance(
            spec=g_spec, 
            current_value=default, 
            trend="none",
            confidence=confidence
        )

    return ObjectInstance(type=obj_type, parts=parts, global_attributes=g_attrs)
