from pathlib import Path

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def test_behavior_turn_on_ok(tmp_path: Path):
    """Test behavior-based turn_on action on flashlight."""
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)
    load_actions(str(Path.cwd() / "kb" / "actions"), rm)

    obj = rm.objects.get("flashlight")

    # Create behavior-enhanced action
    action = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    assert action is not None, "Should find turn_on action for flashlight"

    inst = instantiate_default(obj, rm)
    # Ensure known battery level for this test
    inst.parts["battery"].attributes["level"].current_value = "medium"
    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {})
    assert result.status == "ok"
    assert result.after is not None
    after = result.after
    assert after.parts["switch"].attributes["position"].current_value == "on"


def test_constraint_violation_bulb_on_empty_battery(tmp_path: Path):
    """Test constraint enforcement: bulb can't be on with empty battery."""
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)
    load_actions(str(Path.cwd() / "kb" / "actions"), rm)

    obj = rm.objects.get("flashlight")

    # Create behavior-enhanced action
    action = rm.create_behavior_enhanced_action("flashlight", "turn_on")
    assert action is not None

    # Create flashlight instance with empty battery
    inst = instantiate_default(obj, rm)
    inst.parts["battery"].attributes["level"].current_value = "empty"

    # Try to apply turn_on action
    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {})

    # Action now succeeds but produces no light when the battery is empty
    assert result.status == "ok"
    assert result.after is not None
    bulb_state = result.after.parts["bulb"].attributes["state"].current_value
    brightness = result.after.parts["bulb"].attributes["brightness"].current_value
    assert bulb_state == "off"
    assert brightness == "none"
