from pathlib import Path

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _setup_rm():
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)
    load_actions(str(Path.cwd() / "kb" / "actions"), rm)
    return rm


def test_behavior_turn_off_ok(tmp_path: Path):
    rm = _setup_rm()

    obj = rm.objects.get("flashlight")
    turn_on = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    turn_off = rm.create_behavior_enhanced_action("flashlight", "turn_off")
    assert turn_on is not None
    assert turn_off is not None

    inst = instantiate_default(obj, rm)
    # Ensure battery has a known, non-empty level for turn_on
    inst.parts["battery"].attributes["level"].current_value = "medium"
    engine = TransitionEngine(rm)

    # turn_on first (precondition: switch off, battery not empty)
    r1 = engine.apply_action(inst, turn_on, {})
    assert r1.status == "ok"
    after_on = r1.after
    assert after_on is not None
    assert after_on.parts["switch"].attributes["position"].current_value == "on"
    assert after_on.parts["bulb"].attributes["state"].current_value == "on"

    # turn_off (should reset state and trend)
    r2 = engine.apply_action(after_on, turn_off, {})
    assert r2.status == "ok"
    after_off = r2.after
    assert after_off is not None
    assert after_off.parts["switch"].attributes["position"].current_value == "off"
    assert after_off.parts["bulb"].attributes["state"].current_value == "off"
    assert after_off.parts["bulb"].attributes["brightness"].current_value == "none"
    assert after_off.parts["battery"].attributes["level"].trend == "none"
