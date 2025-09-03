from pathlib import Path
from simulator.core.registries import RegistryManager
from simulator.io.loaders.yaml_loader import load_spaces
from simulator.io.loaders.object_loader import load_object_types, instantiate_default


def test_load_types_v2(tmp_path: Path):
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)

    obj = rm.objects.get("flashlight")
    assert obj.name == "flashlight"
    # battery.level space should exist
    assert rm.spaces.get("battery_level").levels == ["empty", "low", "medium", "high", "full"]

    inst = instantiate_default(obj, rm)
    # Defaults from YAML
    assert inst.parts["battery"].attributes["level"].current_value == "medium"
