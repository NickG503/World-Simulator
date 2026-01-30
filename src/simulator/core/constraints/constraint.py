"""Constraint system for object-level rules enforcement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from pydantic import BaseModel

from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.specs import build_condition_from_raw
from simulator.core.engine.context import EvaluationContext
from simulator.core.objects import ObjectInstance


class Constraint(BaseModel, ABC):
    """Base class for all constraints."""

    type: str

    @abstractmethod
    def evaluate(self, instance: ObjectInstance, registries=None) -> bool:
        """Check if this constraint is satisfied by the current instance state."""
        pass

    @abstractmethod
    def describe(self) -> str:
        """Human-readable description of this constraint."""
        pass


class DependencyConstraint(Constraint):
    """Constraint that enforces: if condition is true, then requirement must also be true."""

    type: str = "dependency"
    condition: Condition  # Structured condition
    requires: Condition  # Structured condition

    def evaluate(self, instance: ObjectInstance, registries=None) -> bool:
        """Check if dependency constraint is satisfied."""
        if registries is None:
            raise ValueError("registries required to evaluate constraints")
        ctx = EvaluationContext(instance=instance, action=None, parameters={}, registries=registries)
        if not self.condition.evaluate(ctx):
            return True  # Condition false = constraint trivially satisfied
        return self.requires.evaluate(ctx)

    def describe(self) -> str:
        def _cond_to_text(c: Condition) -> str:
            from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
            from simulator.utils.error_formatting import get_operator_symbol

            if isinstance(c, AttributeCondition):
                op = get_operator_symbol(c.operator)
                return f"{c.target.to_string()} {op} {c.value}"
            return c.__class__.__name__

        return f"If {_cond_to_text(self.condition)}, then {_cond_to_text(self.requires)}"


class BranchingConstraint(Constraint):
    """Constraint that creates branches based on atomic state conditions.

    When the condition attribute is a value set, this constraint creates
    separate branches for matching (IF) and non-matching (ELSE) values.
    Effects are applied to IF branch, else_effects are applied to ELSE branch.
    """

    type: str = "branching_constraint"
    name: str | None = None  # Optional name for visualization
    condition: Condition  # IF condition (typically AttributeCondition)
    effects: List[Any]  # List of Effect objects to apply when condition is true (IF)
    else_effects: List[Any] = []  # List of Effect objects to apply when condition is false (ELSE)

    model_config = {"arbitrary_types_allowed": True}

    def evaluate(self, instance: ObjectInstance, registries=None) -> bool:
        """Branching constraints don't evaluate as pass/fail - they create branches."""
        # This constraint type creates branches rather than returning pass/fail
        # The actual branching logic is handled in constraint_branching.py
        return True

    def describe(self) -> str:
        def _cond_to_text(c: Condition) -> str:
            from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
            from simulator.utils.error_formatting import get_operator_symbol

            if isinstance(c, AttributeCondition):
                op = get_operator_symbol(c.operator)
                return f"{c.target.to_string()} {op} {c.value}"
            return c.__class__.__name__

        name_part = f"[{self.name}] " if self.name else ""
        return f"{name_part}If {_cond_to_text(self.condition)}, apply {len(self.effects)} effects"

    def get_condition_attribute(self) -> str | None:
        """Get the attribute path from the condition."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        if isinstance(self.condition, AttributeCondition):
            return self.condition.target.to_string()
        return None

    def get_condition_value(self) -> Any:
        """Get the expected value from the condition."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        if isinstance(self.condition, AttributeCondition):
            return self.condition.value
        return None

    def get_condition_operator(self) -> str | None:
        """Get the operator from the condition."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition

        if isinstance(self.condition, AttributeCondition):
            return self.condition.operator
        return None


class ConstraintViolation(BaseModel):
    """Represents a constraint violation."""

    constraint: Constraint
    instance: ObjectInstance
    message: str

    def __str__(self) -> str:
        return f"Constraint violation: {self.message}"


class ConstraintEngine:
    """Engine for evaluating constraints on object instances."""

    def __init__(self):
        self.constraint_factories = {
            "dependency": DependencyConstraint,
            "branching_constraint": BranchingConstraint,
        }

    def create_constraint(self, constraint_data: Dict[str, Any]) -> Constraint:
        """Create a constraint from YAML data."""
        constraint_type = constraint_data.get("type")
        if constraint_type not in self.constraint_factories:
            raise ValueError(f"Unknown constraint type: {constraint_type}")

        # Convert nested condition dicts to Condition instances
        data = dict(constraint_data)
        if constraint_type == "dependency":
            data["condition"] = build_condition_from_raw(data.get("condition"))
            data["requires"] = build_condition_from_raw(data.get("requires"))
        elif constraint_type == "branching_constraint":
            data["condition"] = build_condition_from_raw(data.get("condition"))
            # Effects are handled separately during branching
            data["effects"] = data.get("effects", [])
        factory = self.constraint_factories[constraint_type]
        return factory(**data)

    def validate_instance(
        self, instance: ObjectInstance, constraints: List[Constraint], registries=None
    ) -> List[ConstraintViolation]:
        """Validate an instance against a list of constraints."""
        violations = []

        for constraint in constraints:
            try:
                if not constraint.evaluate(instance, registries=registries):
                    violation = ConstraintViolation(
                        constraint=constraint,
                        instance=instance,
                        message=f"Constraint violated: {constraint.describe()}",
                    )
                    violations.append(violation)
            except Exception as e:
                violation = ConstraintViolation(
                    constraint=constraint,
                    instance=instance,
                    message=f"Error evaluating constraint '{constraint.describe()}': {str(e)}",
                )
                violations.append(violation)

        return violations
