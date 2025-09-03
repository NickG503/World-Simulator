from pathlib import Path
from simulator.core.registries import RegistryManager
from simulator.io.loaders.yaml_loader import load_spaces
from simulator.io.loaders.object_loader import load_object_types, instantiate_default
from simulator.io.loaders.action_loader import load_actions
from simulator.core.engine import TransitionEngine


def test_capability_turn_on_ok(tmp_path: Path):
    """Test capability-based turn_on action on flashlight."""
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)
    load_actions(str(Path.cwd() / "kb" / "actions"), rm)
    
    # Detect capabilities
    rm.detect_and_register_capabilities()

    obj = rm.objects.get("flashlight")
    
    # Find compatible turn_on action
    compatible_actions = rm.find_compatible_actions("flashlight", "turn_on")
    assert len(compatible_actions) > 0, "No compatible turn_on actions found"
    
    action = rm.actions.get(compatible_actions[0])

    inst = instantiate_default(obj, rm)
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
    
    # Detect capabilities
    rm.detect_and_register_capabilities()

    obj = rm.objects.get("flashlight")
    
    # First drain the battery
    drain_action = rm.actions.get("flashlight/drain_battery")
    inst = instantiate_default(obj, rm)
    engine = TransitionEngine(rm)
    drain_result = engine.apply_action(inst, drain_action, {})
    assert drain_result.status == "ok"
    
    # Now try to force bulb on (should violate constraint)
    force_action = rm.actions.get("flashlight/force_bulb_on")
    force_result = engine.apply_action(drain_result.after, force_action, {})
    assert force_result.status == "constraint_violated"
    assert len(force_result.violations) > 0
    assert "bulb.state == on" in force_result.violations[0]
