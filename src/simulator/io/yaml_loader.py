from __future__ import annotations
import os, glob, yaml
from typing import Dict, Any
from simulator.core.quantity import QuantitySpace
from simulator.core.attributes import AttributeType
from simulator.core.object_types import ObjectType
from simulator.core.registry import Registry


def load_object_types(path: str) -> Registry:
    """Load all object types from YAML files under `path` into a Registry."""
    reg = Registry()
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        obj = _parse_object_type(data, source=fp)
        reg.add_object_type(obj)
    return reg


def _parse_object_type(data: Dict[str, Any], source: str) -> ObjectType:
    if "type" not in data or "version" not in data:
        raise ValueError(f"{source}: missing 'type' or 'version'")
    name = data["type"]
    version = int(data["version"])
    attrs_raw = data.get("attributes", {})
    if not isinstance(attrs_raw, dict) or not attrs_raw:
        raise ValueError(f"{source}: 'attributes' must be a non-empty mapping")
    attrs: Dict[str, AttributeType] = {}
    for attr_name, spec in attrs_raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{source}: attribute '{attr_name}' spec must be a mapping")
        space_levels = spec.get("space")
        if not isinstance(space_levels, list) or not space_levels:
            raise ValueError(f"{source}: attribute '{attr_name}' requires non-empty 'space' list")
        space = QuantitySpace(name=f"{name}.{attr_name}", levels=[str(x) for x in space_levels])
        mutable = bool(spec.get("mutable", True))
        default = spec.get("default", None)
        if default is not None:
            default = str(default)
        attrs[attr_name] = AttributeType(name=attr_name, space=space, mutable=mutable, default=default)
    return ObjectType(name=name, version=version, attributes=attrs)