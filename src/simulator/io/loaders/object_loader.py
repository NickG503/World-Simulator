from __future__ import annotations

import glob
import os
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from simulator.core.attributes import AttributeInstance
from simulator.core.objects import PartInstance
from simulator.core.objects.file_spec import ObjectFileSpec
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.objects.object_type import ObjectType
from simulator.core.registries.registry_manager import RegistryManager
from simulator.io.loaders.errors import LoaderError


def _read_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_object_types(path: str, registries: RegistryManager) -> None:
    if not os.path.exists(path):
        return
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        data = _read_yaml(fp)
        try:
            spec = ObjectFileSpec.model_validate(data)
        except ValidationError as exc:
            raise LoaderError(fp, "Invalid object definition", cause=exc) from exc
        try:
            obj_type = spec.build_object_type()
        except Exception as exc:
            raise LoaderError(fp, "Failed to build object type", cause=exc) from exc
        try:
            registries.objects.register(obj_type.name, obj_type)
        except Exception as exc:
            raise LoaderError(fp, f"Failed to register object type '{obj_type.name}'", cause=exc) from exc


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
                last_known = None
                last_trend = None
            else:
                default = a_spec.default_value if a_spec.default_value is not None else space.levels[0]
                confidence = 1.0
                last_known = default
                last_trend = None

            attrs[a_name] = AttributeInstance(
                spec=a_spec,
                current_value=default,
                trend="none",
                confidence=confidence,
                last_known_value=last_known,
                last_trend_direction=last_trend,
            )
        parts[p_name] = PartInstance(spec=p_spec, attributes=attrs)

    g_attrs: Dict[str, AttributeInstance] = {}
    for g_name, g_spec in obj_type.global_attributes.items():
        space = registries.spaces.get(g_spec.space_id)
        # Handle 'unknown' as a special default value
        if g_spec.default_value == "unknown":
            default = "unknown"
            confidence = 0.0  # Unknown values have no confidence
            last_known = None
            last_trend = None
        else:
            default = g_spec.default_value if g_spec.default_value is not None else space.levels[0]
            confidence = 1.0
            last_known = default
            last_trend = None

        g_attrs[g_name] = AttributeInstance(
            spec=g_spec,
            current_value=default,
            trend="none",
            confidence=confidence,
            last_known_value=last_known,
            last_trend_direction=last_trend,
        )

    return ObjectInstance(type=obj_type, parts=parts, global_attributes=g_attrs)
