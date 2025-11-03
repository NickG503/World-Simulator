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
    violations: List[str] = Field(default_factory=list)  # Constraint violation messages
    clarifications: List[str] = Field(default_factory=list)  # Questions needed to resolve unknowns

    @classmethod
    def rejected(
        cls,
        reason: str,
        before: ObjectInstance,
        *,
        clarifications: List[str] | None = None,
    ) -> "TransitionResult":
        return cls(
            before=before,
            after=None,
            status="rejected",
            reason=reason,
            changes=[],
            clarifications=clarifications or [],
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
    """Handles state transitions with clear separation of concerns."""

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
            except Exception as e:  # pragma: no cover - defensive
                _ = e
                continue
        if constraints:
            obj_type.compiled_constraints.extend(constraints)
        self._constraint_cache[object_type] = constraints
        return constraints

    def validate_parameters(self, action: Action, parameters: Dict[str, Any]) -> Optional[str]:
        # Ensure required params are present and values valid when choices provided
        for name, spec in action.parameters.items():
            if spec.required and name not in parameters:
                return f"Missing required parameter: {name}"
            if spec.choices is not None and name in parameters and parameters[name] not in spec.choices:
                return f"Parameter {name} must be one of {spec.choices}"
        return None

    def apply_action(self, instance: ObjectInstance, action: Action, parameters: Dict[str, Any]) -> TransitionResult:
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

        # Phase 3: Check preconditions
        # Use smart evaluation for each precondition to enable short-circuit logic
        for condition in action.preconditions:
            ok = False
            try:
                ok = self.condition_evaluator.evaluate(condition, eval_ctx)
            except Exception:
                # If evaluation crashed due to unknown value in ordered comparison, treat as not ok
                ok = False

            if not ok:
                # Check if this failure is due to an unknown value (using smart evaluation)
                clars = self._clarify_if_unknown(condition, eval_ctx)
                if clars:
                    # Add structure message
                    structure = self._describe_condition_structure(condition)
                    clars.insert(0, f"[INFO] Precondition structure: {structure}")

                    return TransitionResult.rejected(
                        "Precondition requires clarification",
                        before=instance,
                        clarifications=clars,
                    )
                else:
                    # True failure (not due to unknown)
                    failure_msg = self._create_failure_message(condition, eval_ctx)
                    return TransitionResult.rejected(
                        f"Precondition failed: {failure_msg}", before=instance, clarifications=[]
                    )

        # Phase 3.5: Check effect conditions for unknowns
        effect_clarifications = self._clarify_effect_conditions(action.effects, eval_ctx)
        if effect_clarifications:
            return TransitionResult.rejected(
                f"Postcondition requires clarification ({len(effect_clarifications)} attribute(s))",
                before=instance,
                clarifications=effect_clarifications,
            )

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
                # Check for conditional effect failure (no else branch)
                if c.kind == "error" and c.attribute == "[CONDITIONAL_EVAL_FAILED]":
                    return TransitionResult.rejected(f"Postcondition failed: {c.after}", before=instance)
                changes.append(DiffEntry(attribute=c.attribute, before=c.before, after=c.after, kind=c.kind))

        # Phase 5: Check constraints on the new state (cached)
        constraints = self._get_constraints(new_instance.type.name)

        violations = self.constraint_engine.validate_instance(new_instance, constraints, registries=self.registries)
        if violations:
            violation_messages = [str(v) for v in violations]
            return TransitionResult.constraint_violated(
                before=instance, after=new_instance, changes=changes, violations=violation_messages
            )

        return TransitionResult.success(before=instance, after=new_instance, changes=changes)

    def _create_failure_message(self, condition, eval_ctx) -> str:
        """Create detailed failure message with resolved parameter values."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            ImplicationCondition,
            LogicalCondition,
        )
        from simulator.core.actions.conditions.parameter_conditions import (
            ParameterEquals,
            ParameterValid,
        )

        try:
            if isinstance(condition, AttributeCondition):
                # Get actual and expected values with parameter resolution
                actual_value = eval_ctx.read_attribute(condition.target)
                if hasattr(condition.value, "name"):  # Parameter reference
                    expected_value = eval_ctx.parameters.get(condition.value.name)
                    resolved_value_str = str(expected_value)
                else:
                    expected_value = condition.value
                    resolved_value_str = str(condition.value)

                # Create human-readable description
                op_map = {
                    "equals": ("should be", "but got"),
                    "not_equals": ("should not be", "but got"),
                    "lt": ("should be less than", "but got"),
                    "lte": ("should be at most", "but got"),
                    "gt": ("should be greater than", "but got"),
                    "gte": ("should be at least", "but got"),
                }
                if condition.operator in op_map:
                    should_be, but_got = op_map[condition.operator]
                    return f"{condition.target.to_string()} {should_be} {resolved_value_str}, {but_got} {actual_value}"
                else:
                    # Fallback for unknown operators
                    return f"{condition.target.to_string()} {condition.operator} {resolved_value_str} (current: '{actual_value}', target: '{expected_value}')"  # noqa: E501

            elif isinstance(condition, ParameterEquals):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' == '{condition.value}' (current: '{actual_value}', target: '{condition.value}')"  # noqa: E501

            elif isinstance(condition, ParameterValid):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' in {condition.valid_values} (current: '{actual_value}', valid: {condition.valid_values})"  # noqa: E501

            elif isinstance(condition, LogicalCondition):
                # For logical conditions, just use the describe method (complex to resolve all nested conditions)
                return condition.describe()

            elif isinstance(condition, ImplicationCondition):
                return condition.describe()

        except Exception as e:
            # Fallback to basic description
            return f"{condition.describe()} (error resolving details: {e})"

        # Fallback
        return condition.describe()

    def _clarify_if_unknown(self, condition, eval_ctx) -> List[str]:
        """If a precondition depends on an unknown attribute value, produce clarification questions.

        Returns list of question strings using smart evaluation for OR/AND logic.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import LogicalCondition

        # If it's a simple AttributeCondition, use simple check
        if isinstance(condition, AttributeCondition):
            try:
                lhs = eval_ctx.read_attribute(condition.target)
                if isinstance(lhs, str) and lhs == "unknown":
                    return [f"Precondition: what is {condition.target.to_string()}?"]
            except Exception:
                pass
            return []

        # If it's a LogicalCondition, use smart evaluation
        if isinstance(condition, LogicalCondition):
            # Use smart evaluation but with "Precondition" prefix
            result, clarifications = self._smart_evaluate_condition_for_precond(condition, eval_ctx)
            return clarifications

        # Default: no clarifications
        return []

    def _describe_condition_structure(self, condition) -> str:
        """
        Create human-readable description of condition structure.
        Shows the logical structure in a simple form.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            ImplicationCondition,
            LogicalCondition,
        )

        # Base case: Atomic AttributeCondition
        if isinstance(condition, AttributeCondition):
            target = condition.target.to_string()
            op_map = {
                "equals": "==",
                "not_equals": "!=",
                "lt": "<",
                "lte": "<=",
                "gt": ">",
                "gte": ">=",
            }
            op_symbol = op_map.get(condition.operator, condition.operator)
            value = condition.value
            return f"{target}{op_symbol}{value}"

        # Recursive case: LogicalCondition
        if isinstance(condition, LogicalCondition):
            if condition.operator == "or":
                parts = [self._describe_condition_structure(c) for c in condition.conditions]
                return f"({' OR '.join(parts)})"
            elif condition.operator == "and":
                parts = [self._describe_condition_structure(c) for c in condition.conditions]
                return f"({' AND '.join(parts)})"
            elif condition.operator == "not":
                inner = self._describe_condition_structure(condition.conditions[0])
                return f"NOT({inner})"

        # ImplicationCondition
        if isinstance(condition, ImplicationCondition):
            if_part = self._describe_condition_structure(condition.if_condition)
            then_part = self._describe_condition_structure(condition.then_condition)
            return f"IF {if_part} THEN {then_part}"

        return "complex condition"

    def _smart_evaluate_condition_for_precond(
        self, condition, eval_ctx: EvaluationContext
    ) -> tuple[Optional[bool], List[str]]:
        """
        Smart evaluation for preconditions with short-circuit logic.
        Same as _smart_evaluate_condition but uses "Precondition:" prefix.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            ImplicationCondition,
            LogicalCondition,
        )

        # Base case: Atomic AttributeCondition
        if isinstance(condition, AttributeCondition):
            try:
                attr_value = eval_ctx.read_attribute(condition.target)

                if isinstance(attr_value, str) and attr_value == "unknown":
                    question = f"Precondition: what is {condition.target.to_string()}?"
                    return (None, [question])
                else:
                    result = self.condition_evaluator.evaluate(condition, eval_ctx)
                    return (result, [])
            except Exception:
                question = f"Precondition: what is {condition.target.to_string()}?"
                return (None, [question])

        # Recursive case: LogicalCondition with OR
        if isinstance(condition, LogicalCondition) and condition.operator == "or":
            for sub_cond in condition.conditions:
                result, clarifications = self._smart_evaluate_condition_for_precond(sub_cond, eval_ctx)

                if result is True:
                    return (True, [])
                elif result is False:
                    continue
                else:
                    return (None, clarifications)
            return (False, [])

        # Recursive case: LogicalCondition with AND
        if isinstance(condition, LogicalCondition) and condition.operator == "and":
            for sub_cond in condition.conditions:
                result, clarifications = self._smart_evaluate_condition_for_precond(sub_cond, eval_ctx)

                if result is False:
                    return (False, [])
                elif result is True:
                    continue
                else:
                    return (None, clarifications)
            return (True, [])

        # Recursive case: NOT
        if isinstance(condition, LogicalCondition) and condition.operator == "not":
            if len(condition.conditions) != 1:
                return (None, [])
            result, clarifications = self._smart_evaluate_condition_for_precond(condition.conditions[0], eval_ctx)
            if result is not None:
                return (not result, [])
            else:
                return (None, clarifications)

        # Implication
        if isinstance(condition, ImplicationCondition):
            if_result, if_clarifications = self._smart_evaluate_condition_for_precond(condition.if_condition, eval_ctx)
            if if_result is False:
                return (True, [])
            elif if_result is None:
                return (None, if_clarifications)
            else:
                then_result, then_clarifications = self._smart_evaluate_condition_for_precond(
                    condition.then_condition, eval_ctx
                )
                return (then_result, then_clarifications)

        # Fallback
        try:
            result = self.condition_evaluator.evaluate(condition, eval_ctx)
            return (result, [])
        except Exception:
            return (None, [])

    def _smart_evaluate_condition(self, condition, eval_ctx: EvaluationContext) -> tuple[Optional[bool], List[str]]:
        """
        Smart evaluation of conditions with short-circuit logic for unknowns.

        Returns:
            (result, clarifications) where:
            - result: True/False if fully evaluated, None if needs clarification
            - clarifications: List of questions needed to proceed
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import (
            ImplicationCondition,
            LogicalCondition,
        )

        # Base case: Atomic AttributeCondition
        if isinstance(condition, AttributeCondition):
            try:
                attr_value = eval_ctx.read_attribute(condition.target)

                if isinstance(attr_value, str) and attr_value == "unknown":
                    # Need clarification
                    question = f"Postcondition: what is {condition.target.to_string()}?"
                    return (None, [question])
                else:
                    # Can evaluate
                    result = self.condition_evaluator.evaluate(condition, eval_ctx)
                    return (result, [])
            except Exception:
                # If evaluation fails, treat as need clarification
                question = f"Postcondition: what is {condition.target.to_string()}?"
                return (None, [question])

        # Recursive case: LogicalCondition with OR
        if isinstance(condition, LogicalCondition) and condition.operator == "or":
            for sub_cond in condition.conditions:
                result, clarifications = self._smart_evaluate_condition(sub_cond, eval_ctx)

                if result is True:
                    # Short-circuit: Found TRUE in OR, we're done!
                    return (True, [])

                elif result is False:
                    # This sub-condition is FALSE, continue to next
                    continue

                else:  # result is None
                    # Need clarifications for THIS sub-condition
                    # Ask about it BEFORE checking other conditions
                    return (None, clarifications)

            # All sub-conditions evaluated to FALSE
            return (False, [])

        # Recursive case: LogicalCondition with AND
        if isinstance(condition, LogicalCondition) and condition.operator == "and":
            for sub_cond in condition.conditions:
                result, clarifications = self._smart_evaluate_condition(sub_cond, eval_ctx)

                if result is False:
                    # Short-circuit: Found FALSE in AND, we're done!
                    return (False, [])

                elif result is True:
                    # This sub-condition is TRUE, continue to next
                    continue

                else:  # result is None
                    # Need clarifications for THIS sub-condition
                    # Ask about it BEFORE checking other conditions
                    return (None, clarifications)

            # All sub-conditions evaluated to TRUE
            return (True, [])

        # Recursive case: LogicalCondition with NOT
        if isinstance(condition, LogicalCondition) and condition.operator == "not":
            if len(condition.conditions) != 1:
                return (None, [])  # Invalid, can't evaluate

            result, clarifications = self._smart_evaluate_condition(condition.conditions[0], eval_ctx)

            if result is not None:
                return (not result, [])
            else:
                return (None, clarifications)

        # Recursive case: ImplicationCondition (IF A THEN B = (NOT A) OR B)
        if isinstance(condition, ImplicationCondition):
            # Evaluate the if part first
            if_result, if_clarifications = self._smart_evaluate_condition(condition.if_condition, eval_ctx)

            if if_result is False:
                # If condition is false, implication is true (short-circuit)
                return (True, [])

            elif if_result is None:
                # Need to clarify the if part first
                return (None, if_clarifications)

            else:  # if_result is True
                # If condition is true, check the then part
                then_result, then_clarifications = self._smart_evaluate_condition(condition.then_condition, eval_ctx)
                return (then_result, then_clarifications)

        # Fallback: try to evaluate directly (may throw exception)
        try:
            result = self.condition_evaluator.evaluate(condition, eval_ctx)
            return (result, [])
        except Exception:
            # Can't evaluate, no clarifications available
            return (None, [])

    def _clarify_effect_conditions(self, effects: List, eval_ctx: EvaluationContext) -> List[str]:
        """
        Smart scan of effects for conditions with unknown attributes.
        Uses short-circuit logic to only ask about unknowns that matter.

        Returns list of clarification questions for Postconditions.
        First item will be a structure description if conditions exist.
        """
        from simulator.core.actions.effects.conditional_effects import ConditionalEffect

        clarifications = []
        seen_attributes = set()  # Avoid duplicate questions for same attribute
        condition_structures = []  # Collect condition structures to show

        def scan_effect(effect) -> None:
            """Recursively scan an effect for conditions with unknowns."""
            if isinstance(effect, ConditionalEffect):
                # Get the condition structure for informational message
                structure = self._describe_condition_structure(effect.condition)
                if structure not in condition_structures:
                    condition_structures.append(structure)

                # Use smart evaluation for the condition
                result, clar = self._smart_evaluate_condition(effect.condition, eval_ctx)

                # If we need clarifications, collect them (avoiding duplicates)
                for question in clar:
                    # Extract attribute from question to check for duplicates
                    if "what is " in question:
                        attr_part = question.split("what is ")[-1].rstrip("?").strip()
                        if attr_part not in seen_attributes:
                            seen_attributes.add(attr_part)
                            clarifications.append(question)

                # Recursively scan then/else branches
                # Note: We scan both branches because we don't know which will be taken
                # until the condition is fully evaluated
                then_effects = effect._as_list(effect.then_effect)
                else_effects = effect._as_list(effect.else_effect)
                for e in then_effects + else_effects:
                    scan_effect(e)
            elif isinstance(effect, list):
                for e in effect:
                    scan_effect(e)

        # Scan all effects
        for effect in effects:
            scan_effect(effect)

        # If we have clarifications, prepend the structure information
        if clarifications and condition_structures:
            structure_msg = "Postcondition structure: " + " AND ".join(condition_structures)
            clarifications.insert(0, f"[INFO] {structure_msg}")

        return clarifications
