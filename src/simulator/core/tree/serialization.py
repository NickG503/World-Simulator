"""Serialization utilities for tree simulation visualization.

Provides methods for serializing action definitions, conditions, effects,
constraints, and solver rules into visualization-friendly formats.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from simulator.core.actions.action import Action
    from simulator.core.registries.registry_manager import RegistryManager
    from simulator.core.tree.models import SimulationTree


def serialize_action_definition(action: "Action") -> Dict[str, Any]:
    """Serialize action preconditions and effects for visualization."""
    return {
        "preconditions": _serialize_preconditions(action.preconditions),
        "effects": _serialize_effects(action.effects),
    }


def store_action_definition(tree: "SimulationTree", action: "Action") -> None:
    """Store action definition in the tree for visualization."""
    if action.name not in tree.action_definitions:
        tree.action_definitions[action.name] = serialize_action_definition(action)


def store_constraint_definitions(tree: "SimulationTree", object_type: str, registry_manager: "RegistryManager") -> None:
    """Store constraint definitions in the tree for visualization."""
    from simulator.core.constraints.constraint import BranchingConstraint

    if "constraint" in tree.constraint_definitions:
        return

    obj_type = registry_manager.objects.get(object_type)
    if not obj_type:
        return

    constraint_def: Dict[str, Any] = {"branches": []}

    if obj_type.compiled_constraints:
        branching_constraints = [c for c in obj_type.compiled_constraints if isinstance(c, BranchingConstraint)]
        for bc in branching_constraints:
            branch_def: Dict[str, Any] = {
                "condition": _serialize_condition_for_display(bc.condition),
                "effects": [_serialize_effect_for_display(e) for e in bc.effects],
            }
            if bc.elif_cases:
                branch_def["elif_cases"] = [
                    {
                        "condition": _serialize_condition_for_display(ec.condition),
                        "effects": [_serialize_effect_for_display(e) for e in ec.effects],
                    }
                    for ec in bc.elif_cases
                ]
            if bc.else_effects:
                branch_def["else_effects"] = [_serialize_effect_for_display(e) for e in bc.else_effects]
            constraint_def["branches"].append(branch_def)

    if not constraint_def["branches"] and obj_type.constraints:
        for c in obj_type.constraints:
            if hasattr(c, "type") and c.type == "branching_constraint":
                branch_def = {}
                if hasattr(c, "condition") and c.condition:
                    branch_def["condition"] = _serialize_condition_spec(c.condition)
                if hasattr(c, "effects") and c.effects:
                    branch_def["effects"] = [_serialize_effect_spec(e) for e in c.effects]
                if hasattr(c, "elif_cases") and c.elif_cases:
                    branch_def["elif_cases"] = [
                        {
                            "condition": _serialize_condition_spec(ec.condition) if hasattr(ec, "condition") else {},
                            "effects": [_serialize_effect_spec(e) for e in ec.effects]
                            if hasattr(ec, "effects")
                            else [],
                        }
                        for ec in c.elif_cases
                    ]
                if hasattr(c, "else_effects") and c.else_effects:
                    branch_def["else_effects"] = [_serialize_effect_spec(e) for e in c.else_effects]
                if hasattr(c, "name"):
                    branch_def["name"] = c.name
                constraint_def["branches"].append(branch_def)

    if constraint_def["branches"]:
        tree.constraint_definitions["constraint"] = constraint_def


def store_solver_definitions(tree: "SimulationTree", object_type: str, registry_manager: "RegistryManager") -> None:
    """Store solver rule definitions in the tree for visualization."""
    from simulator.core.solver.solver_branching import get_solver_rules

    if "solver" in tree.solver_definitions:
        return

    rules = get_solver_rules(object_type, registry_manager)
    if not rules:
        return

    solver_def: Dict[str, Any] = {"rules": []}
    for rule in rules:
        rule_def: Dict[str, Any] = {
            "name": rule.name,
            "priority": rule.priority,
            "description": rule.description or rule.describe(),
        }
        if rule.condition:
            rule_def["condition"] = _serialize_condition(rule.condition)
        if rule.precondition:
            rule_def["precondition"] = _serialize_condition(rule.precondition)
        if rule.implies:
            rule_def["implies"] = [_serialize_effect_for_display(e) for e in rule.implies]
        if rule.otherwise:
            rule_def["otherwise"] = [_serialize_effect_for_display(e) for e in rule.otherwise]
        if rule.cases:
            rule_def["cases"] = [
                {
                    "condition": _serialize_condition(case.condition),
                    "implies": [_serialize_effect_for_display(e) for e in case.implies],
                }
                for case in rule.cases
            ]
        solver_def["rules"].append(rule_def)

    tree.solver_definitions["solver"] = solver_def


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize_preconditions(preconditions: List[Any]) -> List[Dict[str, Any]]:
    """Serialize preconditions to a visualization-friendly format."""
    return [_serialize_condition(cond) for cond in preconditions]


def _serialize_condition(cond: Any) -> Dict[str, Any]:
    """Serialize a single condition recursively."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition

    if isinstance(cond, OrCondition):
        return {
            "type": "or",
            "description": cond.describe(),
            "conditions": [_serialize_condition(c) for c in cond.conditions],
        }
    elif isinstance(cond, AndCondition):
        return {
            "type": "and",
            "description": cond.describe(),
            "conditions": [_serialize_condition(c) for c in cond.conditions],
        }
    elif isinstance(cond, AttributeCondition):
        return {
            "type": "attribute_check",
            "attribute": cond.target.to_string(),
            "operator": cond.operator,
            "value": cond.value,
            "description": cond.describe(),
        }
    return {
        "type": "unknown",
        "description": cond.describe() if hasattr(cond, "describe") else str(cond),
    }


def _serialize_effects(effects: List[Any]) -> List[Dict[str, Any]]:
    """Serialize effects to a visualization-friendly format."""
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
    from simulator.core.actions.effects.conditional_effects import ConditionalEffect
    from simulator.core.actions.effects.trend_effects import TrendEffect

    result = []
    is_first_conditional = True

    for effect in effects:
        if isinstance(effect, ConditionalEffect):
            branch_type = "if" if is_first_conditional else "elif"
            is_first_conditional = False

            serialized: Dict[str, Any] = {
                "type": "conditional",
                "branch_type": branch_type,
                "condition": _serialize_condition(effect.condition),
                "then_effects": _serialize_effect_list(effect.then_effect),
            }
            if effect.else_effect:
                serialized["else_effects"] = _serialize_effect_list(effect.else_effect)
            result.append(serialized)
        elif isinstance(effect, SetAttributeEffect):
            result.append({"type": "set_attribute", "target": effect.target.to_string(), "value": effect.value})
        elif isinstance(effect, TrendEffect):
            result.append({"type": "trend", "target": effect.target.to_string(), "direction": effect.direction})
        else:
            result.append({"type": "other", "description": str(effect)})

    return result


def _serialize_effect_list(effects: Any) -> List[Dict[str, Any]]:
    """Serialize a list of effects (or single effect)."""
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
    from simulator.core.actions.effects.conditional_effects import ConditionalEffect
    from simulator.core.actions.effects.trend_effects import TrendEffect

    if effects is None:
        return []

    effect_list = effects if isinstance(effects, list) else [effects]
    result = []

    for effect in effect_list:
        if isinstance(effect, ConditionalEffect):
            serialized: Dict[str, Any] = {
                "type": "conditional",
                "branch_type": "elif",
                "condition": _serialize_condition(effect.condition),
                "then_effects": _serialize_effect_list(effect.then_effect),
            }
            if effect.else_effect:
                serialized["else_effects"] = _serialize_effect_list(effect.else_effect)
            result.append(serialized)
        elif isinstance(effect, SetAttributeEffect):
            result.append({"type": "set_attribute", "target": effect.target.to_string(), "value": effect.value})
        elif isinstance(effect, TrendEffect):
            result.append({"type": "trend", "target": effect.target.to_string(), "direction": effect.direction})
        else:
            result.append({"type": "other", "description": str(effect)})

    return result


def _serialize_condition_spec(condition: Any) -> Dict[str, Any]:
    """Serialize a raw condition spec for display."""
    if hasattr(condition, "type"):
        ctype = condition.type
        if ctype == "attribute_check":
            target = getattr(condition, "target", "")
            operator = getattr(condition, "operator", "equals")
            value = getattr(condition, "value", "")
            op_map = {"equals": "==", "not_equals": "!=", "greater_than": ">", "less_than": "<", "in": "in"}
            op_str = op_map.get(operator, operator)
            return {"description": f"{target} {op_str} {value}"}
    return {"description": str(condition)}


def _serialize_effect_spec(effect: Any) -> Dict[str, Any]:
    """Serialize a raw effect spec for display."""
    if hasattr(effect, "type"):
        etype = effect.type
        if etype == "set_attribute":
            target = getattr(effect, "target", "")
            value = getattr(effect, "value", "")
            return {"target": target, "value": value}
        elif etype == "set_trend":
            target = getattr(effect, "target", "")
            direction = getattr(effect, "direction", "none")
            return {"target": target, "value": f"trend {direction}"}
    return {"target": "unknown", "value": "unknown"}


def _serialize_condition_for_display(condition: Any) -> Dict[str, Any]:
    """Serialize a condition for visualization display."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.utils.error_formatting import get_operator_symbol

    if isinstance(condition, AttributeCondition):
        op_symbol = get_operator_symbol(condition.operator)
        return {
            "type": "attribute_check",
            "attribute": condition.target.to_string(),
            "operator": condition.operator,
            "value": condition.value,
            "description": f"{condition.target.to_string()} {op_symbol} {condition.value}",
        }
    return {"type": condition.__class__.__name__}


def _serialize_effect_for_display(effect: Any) -> Dict[str, Any]:
    """Serialize an effect for visualization display."""
    from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
    from simulator.core.actions.effects.trend_effects import TrendEffect

    if isinstance(effect, SetAttributeEffect):
        return {"type": "set_attribute", "target": effect.target.to_string(), "value": effect.value}
    elif isinstance(effect, TrendEffect):
        return {"type": "set_trend", "target": effect.target.to_string(), "value": f"trend {effect.direction}"}
    return {"type": effect.__class__.__name__}
