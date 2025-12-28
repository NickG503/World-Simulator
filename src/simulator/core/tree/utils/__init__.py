"""
Utility functions for tree-based simulation.

These are pure functions that don't require class state:
- condition_evaluation: Evaluate conditions for specific values
- instance_helpers: Clone and modify object instances
- change_helpers: Build and normalize change records
"""

from simulator.core.tree.utils.change_helpers import (
    build_changes_list,
    build_precondition_error,
    normalize_change,
)
from simulator.core.tree.utils.condition_evaluation import (
    evaluate_condition_for_value,
    get_possible_values_for_attribute,
    get_satisfying_values_for_and_condition,
    get_satisfying_values_for_condition,
)
from simulator.core.tree.utils.instance_helpers import (
    clone_instance_with_multi_values,
    clone_instance_with_values,
    set_attribute_value,
    update_snapshot_attribute,
)

__all__ = [
    # condition_evaluation
    "evaluate_condition_for_value",
    "get_satisfying_values_for_condition",
    "get_satisfying_values_for_and_condition",
    "get_possible_values_for_attribute",
    # instance_helpers
    "clone_instance_with_values",
    "clone_instance_with_multi_values",
    "set_attribute_value",
    "update_snapshot_attribute",
    # change_helpers
    "normalize_change",
    "build_changes_list",
    "build_precondition_error",
]
