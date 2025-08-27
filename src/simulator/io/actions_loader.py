from __future__ import annotations
import os, glob, yaml
from typing import Dict, Any, Tuple
from ..core.actions import ActionType, ParamSpec


def load_actions(path: str) -> Dict[Tuple[str, str], ActionType]:
    actions: Dict[Tuple[str,str], ActionType] = {}
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        action = _parse_action(data, source=fp)
        key = (action.object_type, action.name)
        if key in actions:
            raise ValueError(f"Duplicate action {(action.object_type, action.name)} from {fp}")
        actions[key] = action
    return actions


def _parse_action(data: Dict[str, Any], source: str) -> ActionType:
    missing = [k for k in ("action", "object_type") if k not in data]
    if missing:
        raise ValueError(f"{source}: missing keys {missing}")
    name = str(data["action"]).strip()
    object_type = str(data["object_type"]).strip()
    version = int(data.get("version", 1))

    params_raw = data.get("parameters", {}) or {}
    parameters: Dict[str, ParamSpec] = {}
    for p_name, spec in params_raw.items():
        space = None
        if isinstance(spec, dict) and "space" in spec:
            s = spec["space"]
            if not isinstance(s, list) or not all(isinstance(x, (str, int, float)) for x in s):
                raise ValueError(f"{source}: parameter {p_name} space must be a list of scalars")
            space = [str(x) for x in s]
        parameters[p_name] = ParamSpec(name=p_name, space=space)

    preconditions = [str(x) for x in data.get("preconditions", []) or []]
    effects = [str(x) for x in data.get("effects", []) or []]

    return ActionType(name=name, object_type=object_type, version=version,
                      parameters=parameters, preconditions=preconditions, effects=effects)