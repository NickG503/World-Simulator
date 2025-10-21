from pathlib import Path

from simulator.core.prompt import UnknownValueResolver
from simulator.core.registries import RegistryManager
from simulator.core.engine.transition_engine import TransitionEngine
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
    assert "high" in options
    assert options, "Expected filtered options to be non-empty"
    high_index = space.levels.index("high")
    assert all(space.levels.index(opt) <= high_index for opt in options)
    if "full" in space.levels:
        assert "full" not in options
