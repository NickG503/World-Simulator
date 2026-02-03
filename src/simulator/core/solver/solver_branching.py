"""Branching logic for solver rules with unknown values.

When solver rules encounter value sets, they may need to create branches
to handle different possible outcomes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.attributes import AttributePath
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.solver.rule import SolverRule, compile_solver_rules
from simulator.core.solver.solver_engine import SolverEngine
from simulator.core.types import ChangeDict

if TYPE_CHECKING:
    from simulator.core.tree.models import WorldSnapshot


@dataclass
class SolverBranchInfo:
    """Information about a solver branch."""

    rule_name: Optional[str]
    branch_type: str  # "if", "elif", "else", "none"
    condition_attribute: str
    condition_values: List[str]
    changes: List[ChangeDict]


def get_solver_rules(
    object_type_name: str,
    registry_manager: RegistryManager,
) -> List[SolverRule]:
    """Get compiled solver rules for an object type."""
    obj_type = registry_manager.objects.get(object_type_name)
    if not obj_type:
        return []

    # Check if solver rules are already compiled
    if hasattr(obj_type, "compiled_solver_rules") and obj_type.compiled_solver_rules:
        return obj_type.compiled_solver_rules

    # Check for raw solver specs
    if hasattr(obj_type, "solver_specs") and obj_type.solver_specs:
        rules = compile_solver_rules(obj_type.solver_specs)
        obj_type.compiled_solver_rules = rules
        return rules

    return []


def apply_solver_rules(
    snapshot: "WorldSnapshot",
    object_type_name: str,
    registry_manager: RegistryManager,
) -> List[Tuple["WorldSnapshot", SolverBranchInfo]]:
    """Apply solver rules to a snapshot, potentially creating branches.

    For single values: applies rules directly.
    For value sets on checked attributes: creates branches iteratively
    until all value sets are resolved.

    Args:
        snapshot: The current world snapshot
        object_type_name: Name of the object type
        registry_manager: Registry manager

    Returns:
        List of (modified_snapshot, branch_info) tuples
    """
    rules = get_solver_rules(object_type_name, registry_manager)
    if not rules:
        return [
            (
                snapshot,
                SolverBranchInfo(
                    rule_name=None,
                    branch_type="none",
                    condition_attribute="",
                    condition_values=[],
                    changes=[],
                ),
            )
        ]

    engine = SolverEngine(registry_manager)

    # Iteratively branch until no more value sets need branching
    current_branches = [
        (
            snapshot,
            SolverBranchInfo(
                rule_name=None,
                branch_type="none",
                condition_attribute="",
                condition_values=[],
                changes=[],
            ),
        )
    ]

    max_iterations = 10  # Prevent infinite loops
    for _ in range(max_iterations):
        new_branches: List[Tuple["WorldSnapshot", SolverBranchInfo]] = []
        any_branching = False

        for current_snapshot, current_info in current_branches:
            # Check if any rule conditions involve value sets
            needs_branching, branching_rule, branching_attr, value_set = _check_for_value_sets(
                current_snapshot, rules, registry_manager
            )

            if not needs_branching:
                # No value sets - apply rules directly
                modified, changes = engine.apply_rules(current_snapshot, rules)
                # Merge changes with previous branch info
                all_changes = current_info.changes + changes
                new_branches.append(
                    (
                        modified,
                        SolverBranchInfo(
                            rule_name=current_info.rule_name or None,
                            branch_type=current_info.branch_type if current_info.branch_type != "none" else "if",
                            condition_attribute=current_info.condition_attribute,
                            condition_values=current_info.condition_values,
                            changes=all_changes,
                        ),
                    )
                )
            else:
                # Create branches for this value set
                any_branching = True
                sub_branches = _create_solver_branches(
                    current_snapshot, rules, branching_rule, branching_attr, value_set, engine
                )
                # Merge with parent info
                for sub_snapshot, sub_info in sub_branches:
                    all_changes = current_info.changes + sub_info.changes
                    new_branches.append(
                        (
                            sub_snapshot,
                            SolverBranchInfo(
                                rule_name=sub_info.rule_name,
                                branch_type=sub_info.branch_type,
                                condition_attribute=sub_info.condition_attribute,
                                condition_values=sub_info.condition_values,
                                changes=all_changes,
                            ),
                        )
                    )

        current_branches = new_branches

        if not any_branching:
            break

    return (
        current_branches
        if current_branches
        else [
            (
                snapshot,
                SolverBranchInfo(
                    rule_name=None,
                    branch_type="none",
                    condition_attribute="",
                    condition_values=[],
                    changes=[],
                ),
            )
        ]
    )


def _check_for_value_sets(
    snapshot: "WorldSnapshot",
    rules: List[SolverRule],
    registry_manager: RegistryManager,
) -> Tuple[bool, Optional[SolverRule], str, List[str]]:
    """Check if any rule involves a value set or unknown value that needs branching.

    Returns:
        Tuple of (needs_branching, rule, attribute_path, value_set)
    """
    for rule in rules:
        # Check simple condition
        if rule.condition:
            result = _check_condition_for_value_set(rule.condition, snapshot, registry_manager)
            if result:
                return (True, rule, result[0], result[1])

        # Check case conditions
        for case in rule.cases:
            result = _check_condition_for_value_set(case.condition, snapshot, registry_manager)
            if result:
                return (True, rule, result[0], result[1])

    return (False, None, "", [])


def _check_condition_for_value_set(
    condition: Any,
    snapshot: "WorldSnapshot",
    registry_manager: RegistryManager,
) -> Optional[Tuple[str, List[str]]]:
    """Check if a condition involves a value set or unknown value that needs branching.

    Handles both:
    - Value sets (lists of possible values)
    - "unknown" string values (expanded to all space values)

    Only returns a value set if it would actually cause different branching
    outcomes (some values satisfy the condition, some don't).

    Returns:
        Tuple of (attribute_path, value_set) if branching needed, None otherwise
    """
    if isinstance(condition, AttributeCondition):
        attr_path = condition.target.to_string()
        value = snapshot.get_attribute_value(attr_path)
        expected = condition.value
        operator = condition.operator

        # Handle explicit value sets
        if isinstance(value, list):
            # Check if this value set would cause different outcomes
            # i.e., some values satisfy the condition, some don't
            satisfying = []
            non_satisfying = []
            for v in value:
                if _value_matches_condition(v, expected, operator):
                    satisfying.append(v)
                else:
                    non_satisfying.append(v)

            # Only need branching if there are both satisfying and non-satisfying values
            if satisfying and non_satisfying:
                return (attr_path, value)
            # If all values satisfy or all don't, no branching needed for this condition
            return None

        # Handle "unknown" values - expand to all possible space values
        if value == "unknown":
            # Import here to avoid circular import
            from simulator.core.tree.snapshot_utils import get_all_space_values

            # Get the attribute snapshot to find space_id
            attr_snapshot = snapshot._get_attribute_snapshot(attr_path)
            if attr_snapshot and attr_snapshot.space_id:
                all_values = get_all_space_values(attr_snapshot.space_id, registry_manager)
                if all_values:
                    # Check if these values would cause different outcomes
                    satisfying = [v for v in all_values if _value_matches_condition(v, expected, operator)]
                    non_satisfying = [v for v in all_values if not _value_matches_condition(v, expected, operator)]
                    if satisfying and non_satisfying:
                        return (attr_path, all_values)
            return None

    elif isinstance(condition, (AndCondition, OrCondition)):
        for sub in condition.conditions:
            result = _check_condition_for_value_set(sub, snapshot, registry_manager)
            if result:
                return result

    return None


def _value_matches_condition(value: Any, expected: Any, operator: str) -> bool:
    """Check if a single value matches a condition."""
    if operator == "equals":
        return value == expected
    elif operator == "not_equals":
        return value != expected
    elif operator == "in":
        if isinstance(expected, list):
            return value in expected
        return value == expected
    elif operator == "not_in":
        if isinstance(expected, list):
            return value not in expected
        return value != expected
    return False


def _create_solver_branches(
    snapshot: WorldSnapshot,
    rules: List[SolverRule],
    branching_rule: SolverRule,
    branching_attr: str,
    value_set: List[str],
    engine: SolverEngine,
) -> List[Tuple[WorldSnapshot, SolverBranchInfo]]:
    """Create branches for a value set in solver rules.

    For case-based rules, creates one branch per case (if/elif/else).
    For simple condition rules, creates IF and ELSE branches.
    """
    branches: List[Tuple[WorldSnapshot, SolverBranchInfo]] = []

    # Check if this is a case-based rule
    if branching_rule.is_case_based():
        return _create_case_branches(snapshot, rules, branching_rule, branching_attr, value_set, engine)

    # Simple condition rule - create IF/ELSE branches
    satisfying_values = []
    non_satisfying_values = []

    for value in value_set:
        test_snapshot = deepcopy(snapshot)
        _set_snapshot_value(test_snapshot, branching_attr, value)

        if branching_rule.condition:
            if _evaluate_condition(branching_rule.condition, test_snapshot):
                satisfying_values.append(value)
            else:
                non_satisfying_values.append(value)
        else:
            non_satisfying_values.append(value)

    # Create IF branch (satisfying values)
    if satisfying_values:
        if_snapshot = deepcopy(snapshot)
        if len(satisfying_values) == 1:
            _set_snapshot_value(if_snapshot, branching_attr, satisfying_values[0])
        else:
            _set_snapshot_value(if_snapshot, branching_attr, satisfying_values)

        if_modified, if_changes = engine.apply_rules(if_snapshot, rules)
        branches.append(
            (
                if_modified,
                SolverBranchInfo(
                    rule_name=branching_rule.name,
                    branch_type="if",
                    condition_attribute=branching_attr,
                    condition_values=satisfying_values,
                    changes=if_changes,
                ),
            )
        )

    # Create ELSE branch (non-satisfying values)
    if non_satisfying_values:
        else_snapshot = deepcopy(snapshot)
        if len(non_satisfying_values) == 1:
            _set_snapshot_value(else_snapshot, branching_attr, non_satisfying_values[0])
        else:
            _set_snapshot_value(else_snapshot, branching_attr, non_satisfying_values)

        else_modified, else_changes = engine.apply_rules(else_snapshot, rules)
        branches.append(
            (
                else_modified,
                SolverBranchInfo(
                    rule_name=branching_rule.name,
                    branch_type="else",
                    condition_attribute=branching_attr,
                    condition_values=non_satisfying_values,
                    changes=else_changes,
                ),
            )
        )

    if not branches:
        modified, changes = engine.apply_rules(snapshot, rules)
        return [
            (
                modified,
                SolverBranchInfo(
                    rule_name=None,
                    branch_type="none",
                    condition_attribute="",
                    condition_values=[],
                    changes=changes,
                ),
            )
        ]

    return branches


def _create_case_branches(
    snapshot: WorldSnapshot,
    rules: List[SolverRule],
    branching_rule: SolverRule,
    branching_attr: str,
    value_set: List[str],
    engine: SolverEngine,
) -> List[Tuple[WorldSnapshot, SolverBranchInfo]]:
    """Create branches for a case-based rule (if/elif/else).

    Groups values by which case they match, creating one branch per case.
    """
    branches: List[Tuple[WorldSnapshot, SolverBranchInfo]] = []

    # Group values by which case they match
    # Dict: case_index -> list of values that match this case
    case_values: Dict[int, List[str]] = {}
    unmatched_values: List[str] = []

    for value in value_set:
        test_snapshot = deepcopy(snapshot)
        _set_snapshot_value(test_snapshot, branching_attr, value)

        matched = False
        for case_idx, case in enumerate(branching_rule.cases):
            if _evaluate_condition(case.condition, test_snapshot):
                if case_idx not in case_values:
                    case_values[case_idx] = []
                case_values[case_idx].append(value)
                matched = True
                break  # First matching case wins (elif semantics)

        if not matched:
            unmatched_values.append(value)

    # Create a branch for each case that has matching values
    for case_idx, values in sorted(case_values.items()):
        case_snapshot = deepcopy(snapshot)
        if len(values) == 1:
            _set_snapshot_value(case_snapshot, branching_attr, values[0])
        else:
            _set_snapshot_value(case_snapshot, branching_attr, values)

        case_modified, case_changes = engine.apply_rules(case_snapshot, rules)

        # Determine branch type label
        branch_type = "if" if case_idx == 0 else "elif"

        branches.append(
            (
                case_modified,
                SolverBranchInfo(
                    rule_name=branching_rule.name,
                    branch_type=branch_type,
                    condition_attribute=branching_attr,
                    condition_values=values,
                    changes=case_changes,
                ),
            )
        )

    # Create ELSE branch for unmatched values (otherwise effects)
    if unmatched_values:
        else_snapshot = deepcopy(snapshot)
        if len(unmatched_values) == 1:
            _set_snapshot_value(else_snapshot, branching_attr, unmatched_values[0])
        else:
            _set_snapshot_value(else_snapshot, branching_attr, unmatched_values)

        else_modified, else_changes = engine.apply_rules(else_snapshot, rules)
        branches.append(
            (
                else_modified,
                SolverBranchInfo(
                    rule_name=branching_rule.name,
                    branch_type="else",
                    condition_attribute=branching_attr,
                    condition_values=unmatched_values,
                    changes=else_changes,
                ),
            )
        )

    if not branches:
        modified, changes = engine.apply_rules(snapshot, rules)
        return [
            (
                modified,
                SolverBranchInfo(
                    rule_name=None,
                    branch_type="none",
                    condition_attribute="",
                    condition_values=[],
                    changes=changes,
                ),
            )
        ]

    return branches


def _evaluate_condition(condition: Any, snapshot: WorldSnapshot) -> bool:
    """Evaluate a condition against a snapshot."""
    if isinstance(condition, AttributeCondition):
        attr_path = condition.target.to_string()
        value = snapshot.get_attribute_value(attr_path)
        if value is None:
            return False
        return _matches_condition(value, condition.value, condition.operator)

    elif isinstance(condition, AndCondition):
        return all(_evaluate_condition(c, snapshot) for c in condition.conditions)

    elif isinstance(condition, OrCondition):
        return any(_evaluate_condition(c, snapshot) for c in condition.conditions)

    return False


def _matches_condition(value: Any, expected: Any, operator: str) -> bool:
    """Check if a value matches a condition."""
    if operator == "equals":
        return value == expected
    elif operator == "not_equals":
        return value != expected
    elif operator == "in":
        if isinstance(expected, list):
            return value in expected
        return value == expected
    elif operator == "not_in":
        if isinstance(expected, list):
            return value not in expected
        return value != expected
    return False


def _set_snapshot_value(snapshot: WorldSnapshot, attr_path: str, value: Any) -> None:
    """Set an attribute value in the snapshot."""
    attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
    if attr:
        attr.value = value


__all__ = [
    "SolverBranchInfo",
    "apply_solver_rules",
    "get_solver_rules",
]
