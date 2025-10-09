from simulator.core.actions.action import Action
from simulator.core.actions.file_spec import ActionFileSpec
from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.objects.object_type import ObjectType
from simulator.core.registries import RegistryManager


def _build_action_with_nested_logic() -> Action:
    spec = ActionFileSpec.model_validate(
        {
            "action": "configure_tv",
            "object_type": "dummy",
            "parameters": {
                "mode": {"type": "choice", "required": True},
                "level": {"type": "choice", "required": True},
                "profile": {"type": "choice", "required": True},
            },
            "preconditions": {
                "OR": [
                    {
                        "AND": [
                            {"type": "parameter_equals", "parameter": "mode", "value": "custom"},
                            {"type": "parameter_equals", "parameter": "level", "value": "high"},
                        ]
                    },
                    {
                        "AND": [
                            {"type": "parameter_equals", "parameter": "mode", "value": "auto"},
                            {"type": "parameter_equals", "parameter": "profile", "value": "quiet"},
                        ]
                    },
                ]
            },
            "effects": [],
        }
    )

    return Action(
        name=spec.action,
        object_type=spec.object_type,
        parameters=spec.build_parameters(),
        preconditions=spec.build_preconditions(),
        effects=spec.build_effects(),
    )


def _build_action_with_legacy_any_of() -> Action:
    spec = ActionFileSpec.model_validate(
        {
            "action": "legacy_mode",
            "object_type": "dummy",
            "parameters": {
                "mode": {"type": "choice", "required": True},
                "level": {"type": "choice", "required": True},
            },
            "preconditions": {
                "any_of": [
                    [
                        {"type": "parameter_equals", "parameter": "mode", "value": "custom"},
                        {"type": "parameter_equals", "parameter": "level", "value": "high"},
                    ],
                    {"type": "parameter_equals", "parameter": "mode", "value": "auto"},
                ]
            },
            "effects": [],
        }
    )

    return Action(
        name=spec.action,
        object_type=spec.object_type,
        parameters=spec.build_parameters(),
        preconditions=spec.build_preconditions(),
        effects=spec.build_effects(),
    )


def _make_registry_with_dummy_object() -> tuple[RegistryManager, ObjectType]:
    rm = RegistryManager()
    obj_type = ObjectType(name="dummy", parts={}, global_attributes={})
    rm.objects.register(obj_type.name, obj_type)
    return rm, obj_type


def _make_instance(obj_type: ObjectType) -> ObjectInstance:
    return ObjectInstance(type=obj_type, parts={}, global_attributes={})


def test_nested_and_or_groups_allow_multiple_paths():
    action = _build_action_with_nested_logic()
    rm, obj_type = _make_registry_with_dummy_object()
    engine = TransitionEngine(rm)

    primary_branch = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "custom", "level": "high", "profile": "dynamic"},
    )
    assert primary_branch.status == "ok"

    secondary_branch = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "auto", "level": "low", "profile": "quiet"},
    )
    assert secondary_branch.status == "ok"

    failure_branch = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "custom", "level": "low", "profile": "quiet"},
    )
    assert failure_branch.status == "rejected"
    assert failure_branch.reason


def test_legacy_any_of_format_remains_supported():
    action = _build_action_with_legacy_any_of()
    rm, obj_type = _make_registry_with_dummy_object()
    engine = TransitionEngine(rm)

    result = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "auto", "level": "low"},
    )
    assert result.status == "ok"

    legacy_success = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "custom", "level": "high"},
    )
    assert legacy_success.status == "ok"

    legacy_failure = engine.apply_action(
        _make_instance(obj_type),
        action,
        {"mode": "custom", "level": "low"},
    )
    assert legacy_failure.status == "rejected"
    assert legacy_failure.reason
