"""
Logical conditions module.

Provides compound logical conditions (AND/OR) for combining multiple conditions
in preconditions. These enable branching logic in tree-based simulations.

For preconditions:
- OR: Action succeeds if ANY sub-condition passes (creates N success branches)
- AND: Action succeeds if ALL sub-conditions pass (creates 1 success branch)

De Morgan's law is applied for fail branches:
- NOT(A OR B) = NOT A AND NOT B (single fail branch)
- NOT(A AND B) = NOT A OR NOT B (multiple fail branches)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from pydantic import field_validator

from simulator.core.actions.conditions.base import Condition

if TYPE_CHECKING:
    from simulator.core.engine.context import EvaluationContext


class OrCondition(Condition):
    """
    Disjunction: condition passes if ANY sub-condition passes.

    In tree simulation:
    - Creates N success branches (one per satisfiable disjunct with unknown attrs)
    - Creates 1 fail branch (De Morgan: all must fail)
    """

    conditions: List[Condition]

    @field_validator("conditions", mode="before")
    @classmethod
    def _validate_conditions(cls, v):
        if not v or len(v) < 2:
            raise ValueError("OrCondition requires at least 2 sub-conditions")
        return v

    def evaluate(self, context: "EvaluationContext") -> bool:
        """Returns True if ANY sub-condition evaluates to True."""
        return any(c.evaluate(context) for c in self.conditions)

    def describe(self) -> str:
        """Human-readable description of this OR condition."""
        parts = [c.describe() for c in self.conditions]
        return "(" + " OR ".join(parts) + ")"

    def get_checked_attributes(self) -> List[str]:
        """Get all attribute paths checked by this compound condition."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        attrs: List[str] = []
        for cond in self.conditions:
            if isinstance(cond, AttributeCondition):
                attrs.append(cond.target.to_string())
            elif hasattr(cond, "get_checked_attributes"):
                attrs.extend(cond.get_checked_attributes())
        return attrs

    def get_attribute_conditions(self) -> List["Condition"]:
        """Get all sub-conditions that check attributes."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        result: List[Condition] = []
        for cond in self.conditions:
            if isinstance(cond, AttributeCondition):
                result.append(cond)
            elif hasattr(cond, "get_attribute_conditions"):
                result.extend(cond.get_attribute_conditions())
        return result


class AndCondition(Condition):
    """
    Conjunction: condition passes if ALL sub-conditions pass.

    In tree simulation:
    - Creates 1 success branch (all constraints must be satisfied)
    - Creates N fail branches (De Morgan: any one fails)
    """

    conditions: List[Condition]

    @field_validator("conditions", mode="before")
    @classmethod
    def _validate_conditions(cls, v):
        if not v or len(v) < 2:
            raise ValueError("AndCondition requires at least 2 sub-conditions")
        return v

    def evaluate(self, context: "EvaluationContext") -> bool:
        """Returns True if ALL sub-conditions evaluate to True."""
        return all(c.evaluate(context) for c in self.conditions)

    def describe(self) -> str:
        """Human-readable description of this AND condition."""
        parts = [c.describe() for c in self.conditions]
        return "(" + " AND ".join(parts) + ")"

    def get_checked_attributes(self) -> List[str]:
        """Get all attribute paths checked by this compound condition."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        attrs: List[str] = []
        for cond in self.conditions:
            if isinstance(cond, AttributeCondition):
                attrs.append(cond.target.to_string())
            elif hasattr(cond, "get_checked_attributes"):
                attrs.extend(cond.get_checked_attributes())
        return attrs

    def get_attribute_conditions(self) -> List["Condition"]:
        """Get all sub-conditions that check attributes."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )

        result: List[Condition] = []
        for cond in self.conditions:
            if isinstance(cond, AttributeCondition):
                result.append(cond)
            elif hasattr(cond, "get_attribute_conditions"):
                result.extend(cond.get_attribute_conditions())
        return result


# Rebuild models to handle forward references
def _rebuild_models():
    OrCondition.model_rebuild()
    AndCondition.model_rebuild()


_rebuild_models()

__all__ = ["OrCondition", "AndCondition"]
