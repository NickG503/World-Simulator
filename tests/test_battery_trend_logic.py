from pathlib import Path

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.prompt import UnknownValueResolver
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def test_trend_down_marks_value_unknown_and_limits_choices(tmp_path: Path):
    rm = RegistryManager()
    rm.register_defaults()

    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)

    action = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    assert action is not None

    flashlight = instantiate_default(rm.objects.get("flashlight"), rm)
    battery_attr = flashlight.parts["battery"].attributes["level"]
    battery_attr.current_value = "high"
    battery_attr.last_known_value = "high"

    engine = TransitionEngine(rm)
    result = engine.apply_action(flashlight, action, {})
    assert result.status == "ok"
    assert result.after is not None

    updated_attr = result.after.parts["battery"].attributes["level"]
    assert updated_attr.current_value == "unknown"
    assert updated_attr.trend == "down"
    assert updated_attr.last_known_value == "high"
    assert updated_attr.last_trend_direction == "down"

    resolver = UnknownValueResolver(rm)
    space = rm.spaces.get(updated_attr.spec.space_id)
    options = resolver.get_allowed_levels(updated_attr, space)
    # When trending down from "high", should include "high" and all values below
    assert "high" in options, "Trending down from 'high' should include 'high' in options"
    assert options, "Expected filtered options to be non-empty"
    high_index = space.levels.index("high")
    # All options should be at or below "high"
    assert all(space.levels.index(opt) <= high_index for opt in options)
    if "full" in space.levels:
        assert "full" not in options


def test_trend_direction_flip_overwrites_constraints(tmp_path: Path):
    rm = RegistryManager()
    rm.register_defaults()

    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)

    turn_on = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    turn_off = rm.create_behavior_enhanced_action("flashlight", "turn_off")
    charge = rm.create_behavior_enhanced_action("flashlight", "charge_battery")
    assert turn_on is not None
    assert turn_off is not None
    assert charge is not None

    flashlight = instantiate_default(rm.objects.get("flashlight"), rm)
    battery_attr = flashlight.parts["battery"].attributes["level"]
    battery_attr.current_value = "medium"
    battery_attr.last_known_value = "medium"

    engine = TransitionEngine(rm)
    result_down = engine.apply_action(flashlight, turn_on, {})
    assert result_down.status == "ok" and result_down.after is not None

    drained_attr = result_down.after.parts["battery"].attributes["level"]
    assert drained_attr.current_value == "unknown"
    assert drained_attr.last_known_value == "medium"
    assert drained_attr.last_trend_direction == "down"

    # Ensure bulb is off before charging
    result_off = engine.apply_action(result_down.after, turn_off, {})
    assert result_off.status == "ok" and result_off.after is not None

    # Charging now should request clarification because battery.level is unknown
    result_prompt = engine.apply_action(result_off.after, charge, {})
    assert result_prompt.status == "rejected"
    assert any("battery.level" in clar for clar in result_prompt.clarifications)

    # Simulate answering the clarification with the previous level ("medium")
    clarified_state = result_off.after
    clarified_attr = clarified_state.parts["battery"].attributes["level"]
    clarified_attr.current_value = "medium"
    clarified_attr.last_known_value = "medium"
    clarified_attr.last_trend_direction = None
    clarified_attr.trend = "none"

    # Apply an up-trend using the clarified value
    result_up = engine.apply_action(clarified_state, charge, {})
    assert result_up.status == "ok" and result_up.after is not None

    charged_attr = result_up.after.parts["battery"].attributes["level"]
    assert charged_attr.current_value == "unknown"
    assert charged_attr.last_trend_direction == "up"
    assert charged_attr.last_known_value == "medium"

    resolver = UnknownValueResolver(rm)
    space = rm.spaces.get(charged_attr.spec.space_id)
    options = resolver.get_allowed_levels(charged_attr, space)
    assert "medium" in options
    medium_index = space.levels.index("medium")
    assert all(space.levels.index(opt) >= medium_index for opt in options)


def test_trend_up_after_clarification_uses_new_value(tmp_path: Path):
    rm = RegistryManager()
    rm.register_defaults()

    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)

    turn_on = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    turn_off = rm.create_behavior_enhanced_action("flashlight", "turn_off")
    charge = rm.create_behavior_enhanced_action("flashlight", "charge_battery")
    assert turn_on is not None
    assert turn_off is not None
    assert charge is not None

    flashlight = instantiate_default(rm.objects.get("flashlight"), rm)
    battery_attr = flashlight.parts["battery"].attributes["level"]
    battery_attr.current_value = "medium"
    battery_attr.last_known_value = "medium"

    engine = TransitionEngine(rm)
    result_down = engine.apply_action(flashlight, turn_on, {})
    assert result_down.status == "ok" and result_down.after is not None

    drained_attr = result_down.after.parts["battery"].attributes["level"]
    assert drained_attr.current_value == "unknown"
    assert drained_attr.last_known_value == "medium"
    assert drained_attr.last_trend_direction == "down"

    # Simulate the user clarifying the level to "low"
    clarified_state = result_down.after
    clarified_attr = clarified_state.parts["battery"].attributes["level"]
    clarified_attr.current_value = "low"
    clarified_attr.last_known_value = "low"
    clarified_attr.last_trend_direction = None
    clarified_attr.trend = "none"

    # After clarification, bulb is still on; turn it off before charging
    result_off = engine.apply_action(clarified_state, turn_off, {})
    assert result_off.status == "ok" and result_off.after is not None

    result_up = engine.apply_action(result_off.after, charge, {})
    assert result_up.status == "ok" and result_up.after is not None

    charged_attr = result_up.after.parts["battery"].attributes["level"]
    assert charged_attr.current_value == "unknown"
    assert charged_attr.last_known_value == "low"
    assert charged_attr.last_trend_direction == "up"

    resolver = UnknownValueResolver(rm)
    space = rm.spaces.get(charged_attr.spec.space_id)
    options = resolver.get_allowed_levels(charged_attr, space)
    assert "low" in options
    low_index = space.levels.index("low")
    assert all(space.levels.index(opt) >= low_index for opt in options)
