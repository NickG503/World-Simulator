from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.objects import ObjectInstance
from simulator.core.actions.action import Action
from simulator.core.constraints.constraint import ConstraintEngine, ConstraintViolation, Constraint
from .condition_evaluator import ConditionEvaluator
from .effect_applier import EffectApplier
from .context import EvaluationContext, ApplicationContext


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
    def constraint_violated(cls, before: ObjectInstance, after: ObjectInstance, changes: List[DiffEntry], violations: List[str]) -> "TransitionResult":
        return cls(before=before, after=after, status="constraint_violated", changes=changes, violations=violations)


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
        for condition in action.preconditions:
            ok = False
            try:
                ok = self.condition_evaluator.evaluate(condition, eval_ctx)
            except Exception:
                # If evaluation crashed due to unknown value in ordered comparison, treat as not ok
                ok = False
            if not ok:
                # Create detailed failure message with resolved values
                failure_msg = self._create_failure_message(condition, eval_ctx)
                clar = self._clarify_if_unknown(condition, eval_ctx)
                return TransitionResult.rejected(
                    f"Precondition failed: {failure_msg}", before=instance, clarifications=([clar] if clar else [])
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
                changes.append(DiffEntry(attribute=c.attribute, before=c.before, after=c.after, kind=c.kind))

        # Phase 5: Check constraints on the new state (cached)
        constraints = self._get_constraints(new_instance.type.name)
        
        violations = self.constraint_engine.validate_instance(new_instance, constraints, registries=self.registries)
        if violations:
            violation_messages = [str(v) for v in violations]
            return TransitionResult.constraint_violated(
                before=instance, 
                after=new_instance, 
                changes=changes, 
                violations=violation_messages
            )

        return TransitionResult.success(before=instance, after=new_instance, changes=changes)
    
    def _create_failure_message(self, condition, eval_ctx) -> str:
        """Create detailed failure message with resolved parameter values."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.parameter_conditions import ParameterEquals, ParameterValid
        from simulator.core.actions.conditions.logical_conditions import LogicalCondition, ImplicationCondition
        
        try:
            if isinstance(condition, AttributeCondition):
                # Get actual and expected values with parameter resolution
                actual_value = eval_ctx.read_attribute(condition.target)
                if hasattr(condition.value, 'name'):  # Parameter reference
                    expected_value = eval_ctx.parameters.get(condition.value.name)
                    resolved_value_str = str(expected_value)
                else:
                    expected_value = condition.value
                    resolved_value_str = str(condition.value)
                
                # Create description with resolved values
                op_map = {"equals": "==", "not_equals": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
                op_symbol = op_map.get(condition.operator, condition.operator)
                
                return f"{condition.target.to_string()} {op_symbol} {resolved_value_str} (current: '{actual_value}', target: '{expected_value}')"
            
            elif isinstance(condition, ParameterEquals):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' == '{condition.value}' (current: '{actual_value}', target: '{condition.value}')"
            
            elif isinstance(condition, ParameterValid):
                actual_value = eval_ctx.parameters.get(condition.parameter)
                return f"parameter '{condition.parameter}' in {condition.valid_values} (current: '{actual_value}', valid: {condition.valid_values})"
            
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

    def _clarify_if_unknown(self, condition, eval_ctx) -> Optional[str]:
        """If a precondition depends on an unknown attribute value, produce a clarification question.

        Returns a plain question string like "What is battery.level?" or None if not applicable.
        """
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        try:
            if isinstance(condition, AttributeCondition):
                lhs = eval_ctx.read_attribute(condition.target)
                if isinstance(lhs, str) and lhs == "unknown":
                    return f"What is {condition.target.to_string()}?"
        except Exception:
            # Best-effort; if we cannot read, do nothing
            return None
        return None
