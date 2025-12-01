from __future__ import annotations

from typing import Callable, Iterable, List

from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.conditions.parameter_conditions import ParameterEquals, ParameterValid
from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
from simulator.core.actions.effects.base import Effect
from simulator.core.actions.effects.conditional_effects import ConditionalEffect
from simulator.core.actions.effects.trend_effects import TrendEffect
from simulator.core.actions.parameter import ParameterReference
from simulator.core.actions.specs import build_condition
from simulator.core.attributes.attribute_spec import AttributeSpec
from simulator.core.objects.object_type import ObjectType
from simulator.core.objects.part import AttributeTarget
from simulator.core.registries.registry_manager import RegistryManager


class RegistryValidator:
    def __init__(self, registries: RegistryManager):
        self.registries = registries

    def validate_all(self) -> List[str]:
        """Return list of validation errors across registries."""
        errors: List[str] = []
        errors.extend(self._validate_attribute_spaces())
        errors.extend(self._validate_action_references())
        errors.extend(self._validate_object_behaviors())
        errors.extend(self._validate_object_constraints())
        return errors

    def _validate_attribute_spaces(self) -> List[str]:
        """Ensure all attribute specs reference valid spaces."""
        errors: List[str] = []
        for obj_type in self.registries.objects.all():
            # parts
            for part_name, part_spec in obj_type.parts.items():
                for attr_name, attr_spec in part_spec.attributes.items():
                    try:
                        self.registries.spaces.get(attr_spec.space_id)
                    except KeyError:
                        errors.append(
                            f"Object {obj_type.name}.{part_name}.{attr_name} references unknown space: {attr_spec.space_id}"  # noqa: E501
                        )
            # globals
            for g_name, g_spec in obj_type.global_attributes.items():
                try:
                    self.registries.spaces.get(g_spec.space_id)
                except KeyError:
                    errors.append(f"Object {obj_type.name}.{g_name} references unknown space: {g_spec.space_id}")
        return errors

    def _validate_action_references(self) -> List[str]:
        """Ensure action targets and parameter references are valid for target objects."""
        errors: List[str] = []
        for name, action in self.registries.actions.items.items():
            obj_name = action.object_type
            if obj_name.lower() == "generic":
                continue
            try:
                obj_type = self.registries.objects.get(obj_name)
            except KeyError:
                errors.append(f"Action {obj_name}/{action.name} references unknown object type")
                continue

            context = f"Action {obj_name}/{action.name}"
            param_exists = lambda pname: pname in action.parameters

            for condition in action.preconditions:
                errors.extend(
                    self._validate_condition_tree(condition, obj_type, param_exists, f"{context} precondition")
                )
            for effect in action.effects:
                errors.extend(self._validate_effect_tree(effect, obj_type, param_exists, f"{context} effect"))
        return errors

    def _validate_object_constraints(self) -> List[str]:
        errors: List[str] = []
        for obj_type in self.registries.objects.all():
            for idx, constraint in enumerate(obj_type.constraints, start=1):
                context = f"Object {obj_type.name} constraint[{idx}] ({constraint.type})"
                for label, spec in (
                    ("condition", constraint.condition),
                    ("requires", constraint.requires),
                ):
                    if spec is None:
                        continue
                    try:
                        condition = build_condition(spec)
                    except Exception as exc:  # pragma: no cover - defensive
                        errors.append(f"{context}: invalid {label}: {exc}")
                        continue
                    errors.extend(
                        self._validate_condition_tree(
                            condition,
                            obj_type,
                            lambda pname: False,
                            f"{context} {label}",
                        )
                    )
        return errors

    def _validate_object_behaviors(self) -> List[str]:
        errors: List[str] = []
        for obj_type in self.registries.objects.all():
            for name, behavior in obj_type.behaviors.items():
                context_base = f"Object {obj_type.name} behavior '{name}'"
                param_exists = lambda _p: False
                for idx, condition in enumerate(behavior.preconditions, start=1):
                    errors.extend(
                        self._validate_condition_tree(
                            condition,
                            obj_type,
                            param_exists,
                            f"{context_base} precondition[{idx}]",
                        )
                    )
                for idx, effect in enumerate(behavior.effects, start=1):
                    errors.extend(
                        self._validate_effect_tree(
                            effect,
                            obj_type,
                            param_exists,
                            f"{context_base} effect[{idx}]",
                        )
                    )
        return errors

    def _validate_condition_tree(
        self,
        condition: Condition,
        obj_type: ObjectType,
        param_exists: Callable[[str], bool],
        context: str,
    ) -> List[str]:
        """Validate a condition (simplified - only AttributeCondition and parameter conditions)."""
        errors: List[str] = []
        if isinstance(condition, AttributeCondition):
            attr_errors, _ = self._resolve_attribute_spec(obj_type, condition.target, context)
            errors.extend(attr_errors)
            value = getattr(condition, "value", None)
            if isinstance(value, ParameterReference) and not param_exists(value.name):
                errors.append(f"{context}: unknown parameter reference '{value.name}'")
        elif isinstance(condition, (ParameterEquals, ParameterValid)):
            if not param_exists(condition.parameter):
                errors.append(f"{context}: unknown parameter '{condition.parameter}'")
        return errors

    def _validate_effect_tree(
        self,
        effect: Effect,
        obj_type: ObjectType,
        param_exists: Callable[[str], bool],
        context: str,
    ) -> List[str]:
        errors: List[str] = []
        if isinstance(effect, SetAttributeEffect):
            attr_errors, attr_spec = self._resolve_attribute_spec(obj_type, effect.target, context)
            errors.extend(attr_errors)
            if attr_spec is not None and not attr_spec.mutable:
                errors.append(f"{context}: attribute '{effect.target.to_string()}' is immutable")
            if isinstance(effect.value, ParameterReference) and not param_exists(effect.value.name):
                errors.append(f"{context}: unknown parameter reference '{effect.value.name}'")
        elif isinstance(effect, TrendEffect):
            attr_errors, _ = self._resolve_attribute_spec(obj_type, effect.target, context)
            errors.extend(attr_errors)
        elif isinstance(effect, ConditionalEffect):
            errors.extend(
                self._validate_condition_tree(
                    effect.condition,
                    obj_type,
                    param_exists,
                    f"{context} condition",
                )
            )
            for idx, sub_effect in enumerate(self._iter_effects(effect.then_effect), start=1):
                errors.extend(
                    self._validate_effect_tree(
                        sub_effect,
                        obj_type,
                        param_exists,
                        f"{context} then[{idx}]",
                    )
                )
            for idx, sub_effect in enumerate(self._iter_effects(effect.else_effect), start=1):
                errors.extend(
                    self._validate_effect_tree(
                        sub_effect,
                        obj_type,
                        param_exists,
                        f"{context} else[{idx}]",
                    )
                )
        return errors

    @staticmethod
    def _iter_effects(value: Effect | List[Effect] | None) -> Iterable[Effect]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _resolve_attribute_spec(
        self,
        obj_type: ObjectType,
        target: AttributeTarget,
        context: str,
    ) -> tuple[List[str], AttributeSpec | None]:
        if target.part is None:
            if target.attribute not in obj_type.global_attributes:
                return (
                    [f"{context}: unknown global attribute '{target.attribute}' on object '{obj_type.name}'"],
                    None,
                )
            return ([], obj_type.global_attributes[target.attribute])
        if target.part not in obj_type.parts:
            return (
                [f"{context}: unknown part '{target.part}' on object '{obj_type.name}'"],
                None,
            )
        part_spec = obj_type.parts[target.part]
        if target.attribute not in part_spec.attributes:
            return (
                [f"{context}: unknown attribute '{target.attribute}' on part '{target.part}' of '{obj_type.name}'"],
                None,
            )
        return ([], part_spec.attributes[target.attribute])
