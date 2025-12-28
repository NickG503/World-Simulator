"""
Logical conditions module.

Provides compound logical conditions (AND/OR) for combining multiple attribute checks.
This enables checking multiple unknown attributes in a single condition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import Condition

if TYPE_CHECKING:
    from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
    from simulator.core.engine.context import EvaluationContext


class AndCondition(Condition):
    """Logical AND of multiple conditions.

    All sub-conditions must evaluate to True for the AND to be True.

    When used in branching scenarios with unknown attributes:
    - Success branch: ALL attributes are constrained to their satisfying values
    - Fail branch: Original state preserved (action rejected)

    Example YAML:
        type: and
        conditions:
          - type: attribute_check
            target: battery.level
            operator: not_equals
            value: empty
          - type: attribute_check
            target: switch.position
            operator: equals
            value: off
    """

    conditions: List[Condition]

    def evaluate(self, context: "EvaluationContext") -> bool:
        """Evaluate all conditions with AND logic."""
        return all(c.evaluate(context) for c in self.conditions)

    def describe(self) -> str:
        """Human-readable description of this condition."""
        if not self.conditions:
            return "AND()"
        parts = [c.describe() for c in self.conditions]
        return "(" + " AND ".join(parts) + ")"

    def get_checked_attributes(self) -> List[str]:
        """Return all attribute paths checked by sub-conditions.

        This is used by the branching logic to identify which attributes
        are being checked and may need to be constrained.
        """
        from .attribute_conditions import AttributeCondition

        attrs = []
        for c in self.conditions:
            if isinstance(c, AttributeCondition):
                attrs.append(c.target.to_string())
            elif isinstance(c, (AndCondition, OrCondition)):
                # Recursively collect from nested conditions
                attrs.extend(c.get_checked_attributes())
        return attrs

    def get_attribute_conditions(self) -> List["AttributeCondition"]:
        """Return all AttributeCondition instances in this AND.

        Flattens nested conditions.
        """
        from .attribute_conditions import AttributeCondition

        result = []
        for c in self.conditions:
            if isinstance(c, AttributeCondition):
                result.append(c)
            elif isinstance(c, (AndCondition, OrCondition)):
                result.extend(c.get_attribute_conditions())
        return result


class OrCondition(Condition):
    """Logical OR of multiple conditions.

    At least one sub-condition must evaluate to True for the OR to be True.

    When used in branching scenarios with unknown attributes:
    - Creates MULTIPLE success branches, one per disjunct
    - Each success branch has different attribute constraints

    Example YAML:
        type: or
        conditions:
          - type: attribute_check
            target: battery.level
            operator: equals
            value: full
          - type: attribute_check
            target: switch.position
            operator: equals
            value: on
    """

    conditions: List[Condition]

    def evaluate(self, context: "EvaluationContext") -> bool:
        """Evaluate all conditions with OR logic."""
        return any(c.evaluate(context) for c in self.conditions)

    def describe(self) -> str:
        """Human-readable description of this condition."""
        if not self.conditions:
            return "OR()"
        parts = [c.describe() for c in self.conditions]
        return "(" + " OR ".join(parts) + ")"

    def get_checked_attributes(self) -> List[str]:
        """Return all attribute paths checked by sub-conditions."""
        from .attribute_conditions import AttributeCondition

        attrs = []
        for c in self.conditions:
            if isinstance(c, AttributeCondition):
                attrs.append(c.target.to_string())
            elif isinstance(c, (AndCondition, OrCondition)):
                attrs.extend(c.get_checked_attributes())
        return attrs

    def get_attribute_conditions(self) -> List["AttributeCondition"]:
        """Return all AttributeCondition instances in this OR.

        Flattens nested conditions.
        """
        from .attribute_conditions import AttributeCondition

        result = []
        for c in self.conditions:
            if isinstance(c, AttributeCondition):
                result.append(c)
            elif isinstance(c, (AndCondition, OrCondition)):
                result.extend(c.get_attribute_conditions())
        return result


__all__ = ["AndCondition", "OrCondition"]
