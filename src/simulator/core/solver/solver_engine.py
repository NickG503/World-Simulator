"""Solver engine for applying world rules.

The solver engine applies rules in priority order to derive state.
It handles value sets by creating branches when conditions involve unknowns.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import AndCondition, OrCondition
from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
from simulator.core.actions.effects.trend_effects import TrendEffect
from simulator.core.attributes import AttributePath
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.solver.rule import SolverRule
from simulator.core.types import ChangeDict

if TYPE_CHECKING:
    from simulator.core.tree.models import WorldSnapshot


class SolverEngine:
    """Engine for applying solver rules to world state."""

    def __init__(self, registry_manager: RegistryManager):
        self.registry_manager = registry_manager

    def apply_rules(
        self,
        snapshot: "WorldSnapshot",
        rules: List[SolverRule],
    ) -> Tuple["WorldSnapshot", List[ChangeDict]]:
        """Apply solver rules to a snapshot, returning modified snapshot and changes.

        Rules are applied in priority order. Each rule can modify the snapshot.

        Args:
            snapshot: The current world state
            rules: List of solver rules (should be pre-sorted by priority)

        Returns:
            Tuple of (modified_snapshot, list_of_changes)
        """
        modified = deepcopy(snapshot)
        all_changes: List[ChangeDict] = []

        for rule in rules:
            # Check precondition gate
            if rule.precondition:
                if not self._evaluate_condition(rule.precondition, modified):
                    continue

            # Apply the rule
            if rule.is_simple():
                changes = self._apply_simple_rule(modified, rule)
                all_changes.extend(changes)
            elif rule.is_case_based():
                changes = self._apply_case_rule(modified, rule)
                all_changes.extend(changes)

        return modified, all_changes

    def _apply_simple_rule(
        self,
        snapshot: WorldSnapshot,
        rule: SolverRule,
    ) -> List[ChangeDict]:
        """Apply a simple condition->implies/otherwise rule."""
        if not rule.condition:
            # No condition means always apply implies
            return self._apply_effects(snapshot, rule.implies)

        if self._evaluate_condition(rule.condition, snapshot):
            return self._apply_effects(snapshot, rule.implies)
        else:
            return self._apply_effects(snapshot, rule.otherwise)

    def _apply_case_rule(
        self,
        snapshot: WorldSnapshot,
        rule: SolverRule,
    ) -> List[ChangeDict]:
        """Apply a case-based rule (if/elif/else)."""
        # Try each case in order
        for case in rule.cases:
            if self._evaluate_condition(case.condition, snapshot):
                return self._apply_effects(snapshot, case.implies)

        # No case matched - apply otherwise (else)
        return self._apply_effects(snapshot, rule.otherwise)

    def _evaluate_condition(self, condition: Any, snapshot: WorldSnapshot) -> bool:
        """Evaluate a condition against the snapshot.

        For value sets, uses optimistic evaluation (true if any value satisfies).
        """
        if isinstance(condition, AttributeCondition):
            return self._evaluate_attribute_condition(condition, snapshot)
        elif isinstance(condition, AndCondition):
            return all(self._evaluate_condition(c, snapshot) for c in condition.conditions)
        elif isinstance(condition, OrCondition):
            return any(self._evaluate_condition(c, snapshot) for c in condition.conditions)
        return False

    def _evaluate_attribute_condition(
        self,
        condition: AttributeCondition,
        snapshot: WorldSnapshot,
    ) -> bool:
        """Evaluate an attribute condition against the snapshot."""
        attr_path = condition.target.to_string()
        current_value = snapshot.get_attribute_value(attr_path)

        if current_value is None:
            return False

        expected = condition.value
        operator = condition.operator

        # Handle value sets - use optimistic evaluation
        if isinstance(current_value, list):
            return self._evaluate_value_set(current_value, expected, operator)

        return self._evaluate_single_value(current_value, expected, operator)

    def _evaluate_value_set(
        self,
        values: List[str],
        expected: Any,
        operator: str,
    ) -> bool:
        """Evaluate condition for a value set (optimistic - true if any matches)."""
        for value in values:
            if self._evaluate_single_value(value, expected, operator):
                return True
        return False

    def _evaluate_single_value(
        self,
        value: str,
        expected: Any,
        operator: str,
    ) -> bool:
        """Evaluate condition for a single value."""
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

    def _apply_effects(
        self,
        snapshot: WorldSnapshot,
        effects: List[Any],
    ) -> List[ChangeDict]:
        """Apply effects to a snapshot, returning changes."""
        changes: List[ChangeDict] = []

        for effect in effects:
            if isinstance(effect, SetAttributeEffect):
                attr_path = effect.target.to_string()
                old_value = snapshot.get_attribute_value(attr_path)
                new_value = effect.value

                # Set the new value
                self._set_snapshot_value(snapshot, attr_path, new_value)

                if old_value != new_value:
                    changes.append(
                        {
                            "attribute": attr_path,
                            "before": old_value,
                            "after": new_value,
                            "kind": "solver",
                        }
                    )
            elif isinstance(effect, TrendEffect):
                # Handle trend effects
                attr_path = effect.target.to_string()
                old_trend = self._get_snapshot_trend(snapshot, attr_path)
                new_trend = effect.direction

                # Set the new trend
                self._set_snapshot_trend(snapshot, attr_path, new_trend)

                if old_trend != new_trend:
                    changes.append(
                        {
                            "attribute": f"{attr_path}.trend",
                            "before": old_trend,
                            "after": new_trend,
                            "kind": "trend",
                        }
                    )

        return changes

    def _set_snapshot_value(
        self,
        snapshot: WorldSnapshot,
        attr_path: str,
        value: Any,
    ) -> None:
        """Set an attribute value in the snapshot."""
        attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
        if attr:
            attr.value = value

    def _get_snapshot_trend(
        self,
        snapshot: WorldSnapshot,
        attr_path: str,
    ) -> Optional[str]:
        """Get the current trend for an attribute."""
        attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
        if attr:
            return attr.trend
        return None

    def _set_snapshot_trend(
        self,
        snapshot: WorldSnapshot,
        attr_path: str,
        direction: str,
    ) -> None:
        """Set the trend direction for an attribute."""
        attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
        if attr:
            attr.trend = direction
            # Also update last_trend_direction for tracking
            if direction != "none":
                attr.last_trend_direction = direction


__all__ = ["SolverEngine"]
