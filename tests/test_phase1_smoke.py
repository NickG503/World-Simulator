from pathlib import Path
from simulator.io.yaml_loader import load_object_types


def test_load_types(tmp_path: Path):
    kb = Path.cwd() / "kb" / "objects"
    reg = load_object_types(str(kb))
    obj = reg.get("flashlight", 1)
    assert obj.name == "flashlight"
    assert obj.attributes["battery_level"].space.levels == ["empty", "low", "med", "high"]
    state = obj.default_state()
    assert state.values["battery_level"] == "med"