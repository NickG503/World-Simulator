"""Shared error message formatting utilities."""

from typing import List, Union

# Canonical operator symbol mapping - import this instead of duplicating
OPERATOR_SYMBOLS = {
    "equals": "==",
    "not_equals": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "in": "in",
    "not_in": "not in",
}


def get_operator_symbol(operator: str) -> str:
    """Get display symbol for an operator name."""
    return OPERATOR_SYMBOLS.get(operator, operator)


def format_precondition_error(
    attr_path: str,
    operator: str,
    expected_value: Union[str, List[str]],
    actual_value: Union[str, List[str]],
) -> str:
    """
    Format a precondition failure message.

    Args:
        attr_path: Attribute path (e.g., "battery.level")
        operator: Condition operator (e.g., "not_equals")
        expected_value: Expected value from the precondition
        actual_value: Actual value that caused failure

    Returns:
        Formatted message like "battery.level != empty (actual: empty)"
    """
    op_symbol = OPERATOR_SYMBOLS.get(operator, operator)

    # Format actual value (handle lists/sets)
    if isinstance(actual_value, list):
        actual_str = "{" + ", ".join(str(v) for v in actual_value) + "}"
    else:
        actual_str = str(actual_value)

    return f"{attr_path} {op_symbol} {expected_value} (actual: {actual_str})"
