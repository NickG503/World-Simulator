"""
Utility functions for building and normalizing change records.
"""

from typing import Any, Dict, List, Optional

from simulator.core.actions.action import Action


def normalize_change(change: Any) -> Optional[Dict[str, Any]]:
    """Normalize a change (dict or object) to dict format, filtering invalid entries."""
    if isinstance(change, dict):
        attr = change.get("attribute", "")
        before = change.get("before")
        after = change.get("after")
        kind = change.get("kind", "value")
    elif hasattr(change, "attribute"):
        attr = change.attribute
        before = change.before
        after = change.after
        kind = getattr(change, "kind", "value")
    else:
        return None

    # Filter: no-ops, info entries, internal entries
    if before == after or kind == "info" or attr.startswith("["):
        return None

    return {"attribute": attr, "before": before, "after": after, "kind": kind}


def build_changes_list(changes: List[Any]) -> List[Dict[str, Any]]:
    """Build serializable changes list, filtering info/internal/no-op entries."""
    result = []
    for c in changes:
        normalized = normalize_change(c)
        if normalized:
            result.append(normalized)
    return result


def build_precondition_error(
    action: Action,
    attr_path: str,
    actual_values: List[str],
) -> str:
    """Build detailed precondition error message using shared utility."""
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.utils.error_formatting import format_precondition_error

    # Find the precondition that checks this attribute
    for condition in action.preconditions:
        if isinstance(condition, AttributeCondition):
            if condition.target.to_string() == attr_path:
                actual = actual_values[0] if len(actual_values) == 1 else actual_values
                msg = format_precondition_error(
                    attr_path=attr_path,
                    operator=condition.operator,
                    expected_value=condition.value,
                    actual_value=actual,
                )
                return f"Precondition failed: {msg}"

    # Fallback if condition not found
    actual_str = actual_values[0] if len(actual_values) == 1 else "{" + ", ".join(actual_values) + "}"
    return f"Precondition failed: {attr_path} (actual: {actual_str})"
