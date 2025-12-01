"""Formatting helpers for CLI presentation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from rich.table import Table

from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.specs import ConditionSpec, build_condition, build_condition_from_raw
from simulator.core.engine.transition_engine import TransitionResult

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from simulator.core.objects.object_type import ObjectType
    from simulator.core.registries.registry_manager import RegistryManager


def format_condition(condition: Condition | Mapping[str, Any] | None) -> str:
    """Format a condition for display."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.actions.conditions.parameter_conditions import (
        ParameterEquals,
        ParameterValid,
    )
    from simulator.core.actions.parameter import ParameterReference

    if condition is None:
        return "<missing>"

    if isinstance(condition, Mapping):
        try:
            condition = build_condition_from_raw(condition)
        except Exception:  # pragma: no cover - defensive fallback
            ctype = condition.get("type", "condition")
            return f"{ctype} condition"

    # Handle spec objects (e.g., AttributeCheckConditionSpec) that are not yet built
    if isinstance(condition, ConditionSpec):
        try:
            condition = build_condition(condition)
        except Exception:
            # Fallback textual hint; best-effort
            try:
                ctype = getattr(condition, "type", "condition")
                return f"{ctype} condition"
            except Exception:  # pragma: no cover
                return "condition"

    if isinstance(condition, AttributeCondition):
        op_map = {
            "equals": "==",
            "not_equals": "!=",
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
        }
        op_symbol = op_map.get(condition.operator, condition.operator)
        value = condition.value.name if isinstance(condition.value, ParameterReference) else condition.value
        return f"{condition.target.to_string()} {op_symbol} {value}"

    if isinstance(condition, ParameterEquals):
        return f"{condition.parameter} == {condition.value}"

    if isinstance(condition, ParameterValid):
        values = ", ".join(condition.valid_values)
        return f"{condition.parameter} in [{values}]"

    return condition.describe()


def format_constraint(constraint) -> str:
    if constraint.type == "dependency":
        condition_desc = format_condition(constraint.condition)
        requires_desc = format_condition(constraint.requires)
        return f"If {condition_desc}, then {requires_desc}"
    return f"{constraint.type} constraint"


def build_object_definition_table(obj: "ObjectType", registries: "RegistryManager") -> Table:
    table = Table(title="Definition", show_header=True, header_style="bold blue")
    table.add_column("Attribute", style="cyan")
    table.add_column("Default", style="green")
    table.add_column("Mutable", style="dim")

    for part_name, part_spec in obj.parts.items():
        for attr_name, attr_spec in part_spec.attributes.items():
            full_name = f"{part_name}.{attr_name}"
            mutable_icon = "✓" if attr_spec.mutable else "✗"
            default_val = attr_spec.default_value
            if default_val is None:
                space = registries.spaces.get(attr_spec.space_id)
                default_val = space.levels[0]
            table.add_row(full_name, str(default_val), mutable_icon)

    for g_name, g_attr_spec in obj.global_attributes.items():
        mutable_icon = "✓" if g_attr_spec.mutable else "✗"
        default_val = g_attr_spec.default_value
        if default_val is None:
            space = registries.spaces.get(g_attr_spec.space_id)
            default_val = space.levels[0]
        table.add_row(f"global.{g_name}", str(default_val), mutable_icon)

    return table


def build_changes_table(result: TransitionResult) -> Table:
    table = Table(title="Changes")
    table.add_column("Attribute")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Kind")
    for change in result.changes:
        # Skip internal debug markers (e.g., [CONDITIONAL_EVAL])
        if change.attribute and change.attribute.startswith("["):
            continue
        table.add_row(change.attribute or "", str(change.before), str(change.after), change.kind)
    return table


__all__ = [
    "format_condition",
    "format_constraint",
    "build_object_definition_table",
    "build_changes_table",
]
