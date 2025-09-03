from __future__ import annotations
from typing import List
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.objects.object_type import ObjectType
from simulator.core.objects.part import AttributeTarget


class RegistryValidator:
    def __init__(self, registries: RegistryManager):
        self.registries = registries

    def validate_all(self) -> List[str]:
        """Return list of validation errors across registries."""
        errors: List[str] = []
        errors.extend(self._validate_attribute_spaces())
        errors.extend(self._validate_action_references())
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
                            f"Object {obj_type.name}.{part_name}.{attr_name} references unknown space: {attr_spec.space_id}"
                        )
            # globals
            for g_name, g_spec in obj_type.global_attributes.items():
                try:
                    self.registries.spaces.get(g_spec.space_id)
                except KeyError:
                    errors.append(
                        f"Object {obj_type.name}.{g_name} references unknown space: {g_spec.space_id}"
                    )
        return errors

    def _validate_action_references(self) -> List[str]:
        """Ensure action targets and parameter references are valid for target objects."""
        errors: List[str] = []
        for (name, action) in self.registries.actions.items.items():
            # Allow generic actions to skip strict object validation in Phase 1
            obj_name = action.object_type
            if obj_name.lower() == "generic":
                continue
            try:
                obj_type = self.registries.objects.get(obj_name)
            except KeyError:
                errors.append(f"Action {obj_name}/{action.name} references unknown object type")
                continue

            # Validate parameter references
            def _param_exists(pname: str) -> bool:
                return pname in action.parameters

            # Walk conditions/effects for targets and parameter refs
            from simulator.core.actions.conditions.base import Condition
            from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
            from simulator.core.actions.conditions.logical_conditions import LogicalCondition, ImplicationCondition
            from simulator.core.actions.conditions.parameter_conditions import ParameterEquals, ParameterValid
            from simulator.core.actions.effects.base import Effect
            from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
            from simulator.core.actions.effects.trend_effects import TrendEffect
            from simulator.core.actions.effects.conditional_effects import ConditionalEffect
            from simulator.core.actions.parameter import ParameterReference

            def _check_target(obj: ObjectType, tgt: AttributeTarget) -> None:
                if tgt.part is None:
                    if tgt.attribute not in obj.global_attributes:
                        errors.append(f"Action {obj_name}/{action.name}: unknown global attribute target '{tgt.to_string()}'")
                else:
                    if tgt.part not in obj.parts:
                        errors.append(f"Action {obj_name}/{action.name}: unknown part '{tgt.part}' in target '{tgt.to_string()}'")
                    else:
                        if tgt.attribute not in obj.parts[tgt.part].attributes:
                            errors.append(f"Action {obj_name}/{action.name}: unknown attribute '{tgt.attribute}' in part '{tgt.part}'")

            def _check_condition(c: Condition) -> None:
                if isinstance(c, (AttributeCondition,)):
                    _check_target(obj_type, c.target)
                    val = getattr(c, "value", None)
                    if isinstance(val, ParameterReference) and not _param_exists(val.name):
                        errors.append(f"Action {obj_name}/{action.name}: unknown parameter reference '{val.name}' in condition")
                elif isinstance(c, LogicalCondition):
                    for sub in c.conditions:
                        _check_condition(sub)
                elif isinstance(c, ImplicationCondition):
                    _check_condition(c.if_condition)
                    _check_condition(c.then_condition)
                elif isinstance(c, (ParameterEquals, ParameterValid)):
                    # Parameter names must be declared
                    pname = getattr(c, "parameter", None)
                    if pname and not _param_exists(pname):
                        errors.append(f"Action {obj_name}/{action.name}: unknown parameter '{pname}' in condition")

            def _check_effect(e: Effect) -> None:
                if isinstance(e, SetAttributeEffect):
                    _check_target(obj_type, e.target)
                    val = e.value
                    if isinstance(val, ParameterReference) and not _param_exists(val.name):
                        errors.append(f"Action {obj_name}/{action.name}: unknown parameter reference '{val.name}' in effect")
                elif isinstance(e, TrendEffect):
                    _check_target(obj_type, e.target)
                    if e.direction not in ("up", "down", "none"):
                        errors.append(f"Action {obj_name}/{action.name}: invalid trend direction '{e.direction}'")
                elif isinstance(e, ConditionalEffect):
                    _check_condition(e.condition)
                    for se in (e.then_effect if isinstance(e.then_effect, list) else [e.then_effect]):
                        if se is not None:
                            _check_effect(se)
                    if e.else_effect is not None:
                        for se in (e.else_effect if isinstance(e.else_effect, list) else [e.else_effect]):
                            if se is not None:
                                _check_effect(se)

            for cond in action.preconditions:
                _check_condition(cond)
            for eff in action.effects:
                _check_effect(eff)
        return errors

    def _validate_object_constraints(self) -> List[str]:
        # Placeholder: No constraints parsed yet in Phase 1
        return []
