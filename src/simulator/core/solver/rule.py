"""Runtime solver rule classes.

These classes represent compiled solver rules ready for execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.effects.base import Effect
from simulator.core.actions.specs import build_condition, build_effect
from simulator.core.solver.specs import SolverRuleSpec


@dataclass
class SolverCase:
    """A case within a solver rule."""

    condition: Condition
    implies: List[Effect]

    def describe(self) -> str:
        """Human-readable description."""
        effects_desc = ", ".join(str(e) for e in self.implies)
        return f"if {self.condition.describe()} then [{effects_desc}]"


@dataclass
class SolverRule:
    """A compiled solver rule ready for execution.

    Solver rules derive state from other state using implication logic.
    They run after postconditions and after time constraints.

    Attributes:
        name: Unique identifier
        priority: Lower runs first
        description: Human-readable explanation
        precondition: Gate condition - rule only applies if true
        condition: Main condition for simple form
        implies: Effects when condition is true
        otherwise: Effects when condition is false
        cases: if/elif/else branching cases
    """

    name: str
    priority: int = 100
    description: Optional[str] = None
    precondition: Optional[Condition] = None
    condition: Optional[Condition] = None
    implies: List[Effect] = field(default_factory=list)
    otherwise: List[Effect] = field(default_factory=list)
    cases: List[SolverCase] = field(default_factory=list)

    def is_simple(self) -> bool:
        """Check if this is a simple condition->implies rule."""
        return self.condition is not None and not self.cases

    def is_case_based(self) -> bool:
        """Check if this rule uses cases (if/elif/else)."""
        return bool(self.cases)

    def get_checked_attributes(self) -> List[str]:
        """Get all attribute paths checked by this rule."""
        attrs = set()

        if self.precondition:
            attrs.update(self._get_condition_attributes(self.precondition))
        if self.condition:
            attrs.update(self._get_condition_attributes(self.condition))
        for case in self.cases:
            attrs.update(self._get_condition_attributes(case.condition))

        return list(attrs)

    def get_affected_attributes(self) -> List[str]:
        """Get all attribute paths affected by this rule's effects."""
        attrs = set()

        for effect in self.implies:
            if hasattr(effect, "target"):
                attrs.add(effect.target.to_string())
        for effect in self.otherwise:
            if hasattr(effect, "target"):
                attrs.add(effect.target.to_string())
        for case in self.cases:
            for effect in case.implies:
                if hasattr(effect, "target"):
                    attrs.add(effect.target.to_string())

        return list(attrs)

    def _get_condition_attributes(self, condition: Condition) -> List[str]:
        """Extract attribute paths from a condition."""
        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.actions.conditions.logical_conditions import (
            AndCondition,
            OrCondition,
        )

        if isinstance(condition, AttributeCondition):
            return [condition.target.to_string()]
        elif isinstance(condition, (AndCondition, OrCondition)):
            attrs = []
            for sub in condition.conditions:
                attrs.extend(self._get_condition_attributes(sub))
            return attrs
        return []

    def describe(self) -> str:
        """Human-readable description."""
        if self.description:
            return self.description
        if self.is_simple():
            return f"Rule '{self.name}': if {self.condition.describe() if self.condition else 'always'}"
        elif self.is_case_based():
            return f"Rule '{self.name}': {len(self.cases)} cases"
        return f"Rule '{self.name}'"

    @classmethod
    def from_spec(cls, spec: SolverRuleSpec) -> "SolverRule":
        """Build a SolverRule from a SolverRuleSpec."""
        precondition = None
        if spec.precondition:
            precondition = build_condition(spec.precondition)

        condition = None
        if spec.condition:
            condition = build_condition(spec.condition)

        implies = [build_effect(e) for e in spec.implies]
        otherwise = [build_effect(e) for e in spec.otherwise]

        cases = []
        for case_spec in spec.cases:
            case = SolverCase(
                condition=build_condition(case_spec.condition),
                implies=[build_effect(e) for e in case_spec.implies],
            )
            cases.append(case)

        return cls(
            name=spec.name,
            priority=spec.priority,
            description=spec.description,
            precondition=precondition,
            condition=condition,
            implies=implies,
            otherwise=otherwise,
            cases=cases,
        )


def compile_solver_rules(specs: List[SolverRuleSpec]) -> List[SolverRule]:
    """Compile a list of solver rule specs into runtime rules."""
    rules = [SolverRule.from_spec(spec) for spec in specs]
    # Sort by priority (lower first)
    return sorted(rules, key=lambda r: r.priority)


__all__ = [
    "SolverCase",
    "SolverRule",
    "compile_solver_rules",
]
