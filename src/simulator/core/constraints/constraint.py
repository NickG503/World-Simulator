"""Constraint system for object-level rules enforcement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from pydantic import BaseModel

from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.specs import build_condition_from_raw
from simulator.core.engine.condition_evaluator import ConditionEvaluator
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
        """Check if dependency constraint is satisfied using structured conditions."""
        if registries is None:
            raise ValueError("registries required to evaluate constraints")
        evaluator = ConditionEvaluator()
        ctx = EvaluationContext(instance=instance, action=None, parameters={}, registries=registries)
        condition_met = evaluator.evaluate(self.condition, ctx)
        if not condition_met:
            # If condition is false, constraint is trivially satisfied
            return True
        # Condition is true, so requirement must also be true
        return evaluator.evaluate(self.requires, ctx)

    def describe(self) -> str:
        def _cond_to_text(c: Condition) -> str:
            from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
            from simulator.core.actions.conditions.logical_conditions import (
                ImplicationCondition,
                LogicalCondition,
            )

            if isinstance(c, AttributeCondition):
                op_map = {
                    "equals": "==",
                    "not_equals": "!=",
                    "lt": "<",
                    "lte": "<=",
                    "gt": ">",
                    "gte": ">=",
                }
                op = op_map.get(c.operator, c.operator)
                return f"{c.target.to_string()} {op} {c.value}"
            if isinstance(c, LogicalCondition):
                join = f" {c.operator} "
                return "(" + join.join(_cond_to_text(x) for x in c.conditions) + ")"
            if isinstance(c, ImplicationCondition):
                return f"if {_cond_to_text(c.if_condition)} then {_cond_to_text(c.then_condition)}"
            return c.__class__.__name__

        return f"If {_cond_to_text(self.condition)}, then {_cond_to_text(self.requires)}"

    # String expressions removed – constraints must use structured conditions


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
        self.constraint_factories = {"dependency": DependencyConstraint}

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
