from __future__ import annotations
import glob
import os
from typing import Any, Dict, List
import yaml
from simulator.core.actions.action import Action
from simulator.core.actions.parameter import ParameterSpec, ParameterReference
from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.conditions.parameter_conditions import ParameterValid, ParameterEquals
from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import LogicalCondition, ImplicationCondition
from simulator.core.objects import AttributeTarget
from simulator.core.actions.effects.base import Effect
from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
from simulator.core.actions.effects.trend_effects import TrendEffect
from simulator.core.actions.effects.conditional_effects import ConditionalEffect
from simulator.core.registries.registry_manager import RegistryManager


def _read_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _require_fields(data: Dict[str, Any], fields: List[str], ctx: str) -> None:
    missing = [k for k in fields if k not in data]
    if missing:
        raise ValueError(f"Missing required field(s) {missing} in {ctx}")


def _normalize_attr_value(value: Any) -> Any:
    """Normalize YAML scalars for attribute comparisons/assignments.

    - Parameter references pass through
    - Booleans map to binary_state strings ('on'/'off')
    - Everything else becomes a string
    """
    if isinstance(value, dict) and value.get("type") == "parameter_ref":
        return ParameterReference(name=value["name"])  # type: ignore
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _parse_parameter_spec(pname: str, spec: Dict[str, Any]) -> ParameterSpec:
    ptype = spec.get("type", "choice")
    choices = spec.get("choices")
    required = bool(spec.get("required", True))
    return ParameterSpec(name=pname, type=ptype, choices=choices, required=required)


def _parse_condition(data: Dict[str, Any]) -> Condition:
    _require_fields(data, ["type"], "condition")
    ctype = data.get("type")
    if ctype == "parameter_valid":
        _require_fields(data, ["parameter"], "parameter_valid condition")
        return ParameterValid(parameter=data["parameter"], valid_values=list(data.get("valid_values", [])))
    if ctype == "parameter_equals":
        _require_fields(data, ["parameter", "value"], "parameter_equals condition")
        return ParameterEquals(parameter=data["parameter"], value=str(data["value"]))
    if ctype == "attribute_check":
        _require_fields(data, ["target", "operator", "value"], "attribute_check condition")
        target = AttributeTarget.from_string(str(data["target"]))
        op = str(data.get("operator")).strip()
        if op not in ("equals", "not_equals", "lt", "lte", "gt", "gte"):
            raise ValueError(f"Invalid operator '{op}' for attribute_check; expected one of: equals, not_equals, lt, lte, gt, gte")
        value = _normalize_attr_value(data.get("value"))
        return AttributeCondition(target=target, operator=op, value=value)  # type: ignore
    # attribute_equals removed (use attribute_check with operator: equals)
    if ctype == "attribute_equals":
        raise ValueError("'attribute_equals' is removed. Use 'attribute_check' with operator: 'equals'.")
    if ctype == "implication":
        _require_fields(data, ["if", "then"], "implication condition")
        return ImplicationCondition(
            if_condition=_parse_condition(data["if"]),
            then_condition=_parse_condition(data["then"]),
        )
    if ctype in ("and", "or", "not"):
        conds = data.get("conditions", []) or []
        if not isinstance(conds, list):
            raise ValueError("Logical condition 'conditions' must be a list")
        return LogicalCondition(operator=ctype, conditions=[_parse_condition(c) for c in conds])
    raise ValueError(f"Unknown condition type: {ctype}")


def _parse_effect(data: Dict[str, Any]) -> Effect:
    _require_fields(data, ["type"], "effect")
    etype = data.get("type")
    if etype == "set_attribute":
        _require_fields(data, ["target", "value"], "set_attribute effect")
        target = AttributeTarget.from_string(str(data["target"]))
        value = _normalize_attr_value(data.get("value"))
        return SetAttributeEffect(target=target, value=value)  # type: ignore
    if etype == "set_trend":
        _require_fields(data, ["target", "direction"], "set_trend effect")
        target = AttributeTarget.from_string(str(data["target"]))
        direction = str(data["direction"]).lower()
        if direction not in ("up", "down", "none"):
            raise ValueError(f"Invalid trend direction '{direction}' (expected one of: up, down, none)")
        return TrendEffect(target=target, direction=direction)
    if etype == "conditional":
        _require_fields(data, ["condition"], "conditional effect")
        cond = _parse_condition(data["condition"])
        def _parse_effects_list(val: Any) -> List[Effect]:
            effects: List[Effect] = []
            if isinstance(val, list):
                for e in val:
                    if isinstance(e, dict):
                        effects.append(_parse_effect(e))
                return effects
            if isinstance(val, dict):
                return [_parse_effect(val)]
            return []
        then_list = _parse_effects_list(data.get("then"))
        else_list = _parse_effects_list(data.get("else"))
        # ConditionalEffect accepts single or list; we keep lists
        return ConditionalEffect(condition=cond, then_effect=then_list, else_effect=else_list)
    raise ValueError(f"Unknown effect type: {etype}")


def load_actions(path: str, registries: RegistryManager) -> None:
    if not os.path.exists(path):
        return
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        data = _read_yaml(fp)
        name = str(data["action"]).strip()
        object_type = str(data["object_type"]).strip()
        
        # New: capability support
        required_capabilities = set()
        if "required_capabilities" in data:
            cap_list = data["required_capabilities"]
            if isinstance(cap_list, list):
                required_capabilities = set(cap_list)
            elif isinstance(cap_list, str):
                required_capabilities = {cap_list}

        # parameters
        params_raw = data.get("parameters", {}) or {}
        parameters: Dict[str, ParameterSpec] = {}
        for pname, pspec in params_raw.items():
            parameters[pname] = _parse_parameter_spec(pname, pspec)

        # preconditions
        preconditions: List[Condition] = []
        for c in data.get("preconditions", []) or []:
            preconditions.append(_parse_condition(c))

        # effects
        effects: List[Effect] = []
        for e in data.get("effects", []) or []:
            effects.append(_parse_effect(e))

        action = Action(
            name=name,
            object_type=object_type,
            required_capabilities=required_capabilities,
            parameters=parameters,
            preconditions=preconditions,
            effects=effects,
        )
        
        # Register with capability-based key if it's capability-based
        if required_capabilities:
            # Capability-based actions get registered as "capability:{name}"
            key = f"capability:{name}"
        else:
            # Traditional object-specific actions
            key = f"{object_type}/{name}"
        
        registries.actions.register(key, action)
