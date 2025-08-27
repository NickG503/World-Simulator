from pathlib import Path
from simulator.io.yaml_loader import load_object_types
from simulator.io.actions_loader import load_actions
from simulator.core.action_engine import ActionEngine


def test_flip_switch_ok(tmp_path: Path):
    reg = load_object_types(str(Path.cwd() / "kb" / "objects"))
    acts = load_actions(str(Path.cwd() / "kb" / "actions"))
    obj = reg.get("flashlight", 1)
    action = acts[("flashlight", "flip_switch")]

    s = obj.default_state()
    engine = ActionEngine(obj)
    result = engine.apply(s, action, {"to": "on"})
    assert result.status == "ok"
    assert result.after.values["switch"] == "on"
    assert result.after.values["bulb"] == "on"
    assert result.after.trends.get("battery_level") == "down"
    attrs_changed = {d.attribute for d in result.diff}
    assert "switch" in attrs_changed and "bulb" in attrs_changed


def test_flip_switch_reject_empty_battery(tmp_path: Path):
    reg = load_object_types(str(Path.cwd() / "kb" / "objects"))
    acts = load_actions(str(Path.cwd() / "kb" / "actions"))
    obj = reg.get("flashlight", 1)
    action = acts[("flashlight", "flip_switch")]
    s = obj.default_state()
    s.values["battery_level"] = "empty"
    engine = ActionEngine(obj)
    result = engine.apply(s, action, {"to": "on"})
    assert result.status == "rejected"
    assert "Precondition failed" in result.reason