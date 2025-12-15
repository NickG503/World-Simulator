"""
Transition Engine: Handles state transitions for actions.

Simplified for tree-based simulation:
- Preconditions: Binary (pass/fail) based on single attribute check
- Effects: Applied directly, conditional effects select branch based on known values
- No clarification/questioning logic
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from simulator.core.actions.action import Action
from simulator.core.constraints.constraint import Constraint, ConstraintEngine
from simulator.core.objects import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager

from .condition_evaluator import ConditionEvaluator
from .context import ApplicationContext, EvaluationContext
from .effect_applier import EffectApplier


class DiffEntry(BaseModel):
    attribute: str
    before: Optional[str]
    after: Optional[str]
    kind: str  # value or trend


class TransitionResult(BaseModel):
    before: ObjectInstance
    after: Optional[ObjectInstance]
    status: str  # ok, rejected, or constraint_violated
    reason: Optional[str] = None
    changes: List[DiffEntry] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)

    @classmethod
    def rejected(cls, reason: str, before: ObjectInstance) -> "TransitionResult":
        return cls(
            before=before,
            after=None,
            status="rejected",
            reason=reason,
            changes=[],
        )

    @classmethod
    def success(cls, before: ObjectInstance, after: ObjectInstance, changes: List[DiffEntry]) -> "TransitionResult":
        return cls(before=before, after=after, status="ok", changes=changes)

    @classmethod
    def constraint_violated(
        cls,
        before: ObjectInstance,
        after: ObjectInstance,
        changes: List[DiffEntry],
        violations: List[str],
    ) -> "TransitionResult":
        return cls(
            before=before,
            after=after,
            status="constraint_violated",
            changes=changes,
            violations=violations,
        )


class TransitionEngine:
    """Handles state transitions with simplified precondition/effect logic."""

    def __init__(self, registry_manager: RegistryManager):
        self.registries = registry_manager
        self.condition_evaluator = ConditionEvaluator()
        self.effect_applier = EffectApplier()
        self.constraint_engine = ConstraintEngine()
        self._constraint_cache: Dict[str, List[Constraint]] = {}

    def _get_constraints(self, object_type: str) -> List[Constraint]:
        """Create and cache constraints for a given object type."""
        if object_type in self._constraint_cache:
            return self._constraint_cache[object_type]

        obj_type = self.registries.objects.get(object_type)
        if obj_type.compiled_constraints:
            self._constraint_cache[object_type] = obj_type.compiled_constraints
            return obj_type.compiled_constraints

        constraints: List[Constraint] = []
        for constraint_data in obj_type.constraints:
            try:
                constraints.append(self.constraint_engine.create_constraint(constraint_data.model_dump()))
            except Exception:
                continue
        if constraints:
            obj_type.compiled_constraints.extend(constraints)
        self._constraint_cache[object_type] = constraints
        return constraints

    def validate_parameters(self, action: Action, parameters: Dict[str, Any]) -> Optional[str]:
        """Validate action parameters."""
        for name, spec in action.parameters.items():
            if spec.required and name not in parameters:
                return f"Missing required parameter: {name}"
            if spec.choices is not None and name in parameters and parameters[name] not in spec.choices:
                return f"Parameter {name} must be one of {spec.choices}"
        return None

    def apply_action(self, instance: ObjectInstance, action: Action, parameters: Dict[str, Any]) -> TransitionResult:
        """
        Apply an action to an object instance.

        Simplified logic:
        1. Validate parameters
        2. Check preconditions (binary: pass/fail)
        3. Apply effects (conditional effects select branch based on known values)
        4. Check constraints
        """
        # Phase 1: Validate parameters
        err = self.validate_parameters(action, parameters)
        if err:
            return TransitionResult.rejected(err, before=instance)

        # Phase 2: Build evaluation context
        eval_ctx = EvaluationContext(
            instance=instance,
            action=action,
            parameters=parameters,
            registries=self.registries,
        )

        # Phase 3: Check preconditions (binary: all must pass)
        for condition in action.preconditions:
            try:
                ok = self.condition_evaluator.evaluate(condition, eval_ctx)
            except Exception:
                ok = False

            if not ok:
                failure_msg = self._create_failure_message(condition, eval_ctx)
                return TransitionResult.rejected(f"Precondition failed: {failure_msg}", before=instance)

        # Phase 4: Apply effects
        new_instance = instance.deep_copy()
        app_ctx = ApplicationContext.model_construct(
            instance=eval_ctx.instance,
            action=eval_ctx.action,
            parameters=dict(eval_ctx.parameters),
            registries=eval_ctx.registries,
        )
        changes: List[DiffEntry] = []

        for effect in action.effects:
            sc = self.effect_applier.apply(effect, app_ctx, new_instance)
            for c in sc:
                changes.append(DiffEntry(attribute=c.attribute, before=c.before, after=c.after, kind=c.kind))

        # Phase 5: Check constraints on the new state
        constraints = self._get_constraints(new_instance.type.name)

        violations = self.constraint_engine.validate_instance(new_instance, constraints, registries=self.registries)
        if violations:
            violation_messages = [str(v) for v in violations]
            return TransitionResult.constraint_violated(
                before=instance, after=new_instance, changes=changes, violations=violation_messages
            )

        return TransitionResult.success(before=instance, after=new_instance, changes=changes)

    def _create_failure_message(self, condition, eval_ctx) -> str:
        """Create a failure message for a condition."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.parameter_conditions import (
            ParameterEquals,
            ParameterValid,
        )
        from simulator.utils.error_formatting import format_precondition_error

        try:
            if isinstance(condition, AttributeCondition):
                actual_value = eval_ctx.read_attribute(condition.target)
                if hasattr(condition.value, "name"):  # Parameter reference
                    expected_value = eval_ctx.parameters.get(condition.value.name)
                else:
                    expected_value = condition.value

                return format_precondition_error(
                    attr_path=condition.target.to_string(),
                    operator=condition.operator,
                    expected_value=expected_value,
                    actual_value=actual_value,
                )

            elif isinstance(condition, ParameterEquals):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' == '{condition.value}' (actual: '{actual_value}')"

            elif isinstance(condition, ParameterValid):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' in {condition.valid_values} (actual: '{actual_value}')"

        except Exception as e:
            return f"{condition.describe()} (error: {e})"

        return condition.describe()
