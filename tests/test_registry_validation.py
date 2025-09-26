import textwrap

from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _write(path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _setup_spaces(tmp_path):
    spaces_dir = tmp_path / "spaces"
    spaces_dir.mkdir()
    _write(
        spaces_dir / "common.yaml",
        """
        spaces:
          - id: binary_state
            name: Binary
            levels: ["off", "on"]
        """
    )
    return spaces_dir


def test_behavior_mutates_immutable_attribute(tmp_path):
    spaces_dir = _setup_spaces(tmp_path)

    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    _write(
        objects_dir / "lamp.yaml",
        """
        type: lamp
        global_attributes:
          state:
            space: binary_state
            mutable: false
        behaviors:
          turn_on:
            effects:
              - type: set_attribute
                target: state
                value: on
        """
    )

    rm = RegistryManager()
    load_spaces(str(spaces_dir), rm)
    load_object_types(str(objects_dir), rm)

    errors = RegistryValidator(rm).validate_all()
    assert any("immutable" in e for e in errors)


def test_behavior_unknown_attribute(tmp_path):
    spaces_dir = _setup_spaces(tmp_path)

    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    _write(
        objects_dir / "device.yaml",
        """
        type: device
        parts:
          panel:
            attributes:
              button:
                space: binary_state
        behaviors:
          toggle:
            effects:
              - type: set_attribute
                target: panel.switch
                value: on
        """
    )

    rm = RegistryManager()
    load_spaces(str(spaces_dir), rm)
    load_object_types(str(objects_dir), rm)

    errors = RegistryValidator(rm).validate_all()
    assert any("unknown attribute" in e for e in errors)
