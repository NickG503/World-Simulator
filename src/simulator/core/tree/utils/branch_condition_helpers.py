"""
Utility functions for creating BranchCondition objects.

Consolidates repeated BranchCondition creation patterns from branching mixins.
"""

from typing import Dict, List, Literal, Union

from simulator.core.tree.models import BranchCondition


def create_simple_branch_condition(
    attr_path: str,
    values: Union[str, List[str]],
    source: Literal["precondition", "postcondition"],
    branch_type: Literal["if", "elif", "else", "success", "fail"],
) -> BranchCondition:
    """
    Create a simple BranchCondition with correct operator based on value count.

    Args:
        attr_path: Attribute path (e.g., "cube.face")
        values: Single value or list of values
        source: "precondition" or "postcondition"
        branch_type: Type of branch

    Returns:
        BranchCondition with appropriate operator ("equals" for single, "in" for multi)
    """
    if isinstance(values, list):
        if len(values) == 1:
            operator = "equals"
            value = values[0]
        else:
            operator = "in"
            value = values
    else:
        operator = "equals"
        value = values

    return BranchCondition(
        attribute=attr_path,
        operator=operator,
        value=value,
        source=source,
        branch_type=branch_type,
    )


def create_compound_branch_condition(
    attr_constraints: Dict[str, List[str]],
    source: Literal["precondition", "postcondition"],
    branch_type: Literal["if", "elif", "else", "success", "fail"],
    compound_type: Literal["and", "or"],
) -> BranchCondition:
    """
    Create compound BranchCondition from constraint dict.

    Args:
        attr_constraints: Dict of {attr_path: values}
        source: "precondition" or "postcondition"
        branch_type: Type of branch
        compound_type: "and" or "or"

    Returns:
        BranchCondition with sub_conditions for compound, or simple if single attr
    """
    if not attr_constraints:
        raise ValueError("attr_constraints cannot be empty")

    # Build sub-conditions for each attribute
    sub_conditions = []
    for attr_path, values in attr_constraints.items():
        sub_conditions.append(create_simple_branch_condition(attr_path, values, source, branch_type))

    # If only one attribute, return simple condition
    if len(sub_conditions) == 1:
        return sub_conditions[0]

    # Create compound condition
    first = sub_conditions[0]
    return BranchCondition(
        attribute=first.attribute,
        operator=first.operator,
        value=first.value,
        source=source,
        branch_type=branch_type,
        compound_type=compound_type,
        sub_conditions=sub_conditions,
    )


def merge_branch_conditions(
    precond_constraints: Dict[str, List[str]],
    postcond_attr: str,
    postcond_value: Union[str, List[str]],
    postcond_branch_type: Literal["if", "elif", "else"],
) -> BranchCondition:
    """
    Merge precondition constraints and postcondition into compound BranchCondition.

    Used when creating Cartesian product branches.

    Args:
        precond_constraints: Dict of {attr_path: values} for precondition
        postcond_attr: Postcondition attribute path
        postcond_value: Postcondition value(s)
        postcond_branch_type: Type of postcondition branch

    Returns:
        Compound BranchCondition combining precond and postcond
    """
    sub_conditions = []

    # Add precondition sub-conditions
    for attr_path, values in precond_constraints.items():
        sub_conditions.append(create_simple_branch_condition(attr_path, values, "precondition", "success"))

    # Add postcondition sub-condition
    sub_conditions.append(
        create_simple_branch_condition(postcond_attr, postcond_value, "postcondition", postcond_branch_type)
    )

    # If only one condition total, return it directly
    if len(sub_conditions) == 1:
        return sub_conditions[0]

    # Create compound condition
    first = sub_conditions[0]
    return BranchCondition(
        attribute=first.attribute,
        operator=first.operator,
        value=first.value,
        source="precondition",
        branch_type="success",
        compound_type="and",
        sub_conditions=sub_conditions,
    )


def create_fail_branch_condition(
    attr_constraints: Dict[str, List[str]],
    source: Literal["precondition", "postcondition"] = "precondition",
) -> BranchCondition:
    """
    Create a fail branch condition from constraint dict.

    Args:
        attr_constraints: Dict of {attr_path: failing_values}
        source: Source of the condition

    Returns:
        BranchCondition for fail branch (compound AND if multiple attrs)
    """
    return create_compound_branch_condition(
        attr_constraints=attr_constraints,
        source=source,
        branch_type="fail",
        compound_type="and",
    )
