import textwrap

import pytest

from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.errors import LoaderError
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def test_action_loader_schema_validation(tmp_path):
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    (actions_dir / "bad_action.yaml").write_text(
        textwrap.dedent(
            """
            action: faulty
            object_type: widget
            preconditions:
              - target: part.attr
            effects: []
            """
        ),
        encoding="utf-8",
    )

    rm = RegistryManager()

    with pytest.raises(LoaderError):
        load_actions(str(actions_dir), rm)


def test_object_loader_missing_dependency_requires(tmp_path):
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    (objects_dir / "widget.yaml").write_text(
        textwrap.dedent(
            """
            type: widget
            global_attributes:
              state:
                space: binary_state
            constraints:
              - type: dependency
                condition:
                  type: attribute_check
                  target: state
                  operator: equals
                  value: on
            """
        ),
        encoding="utf-8",
    )

    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(tmp_path / "spaces"), rm)  # no extra spaces but call for completeness

    with pytest.raises(LoaderError):
        load_object_types(str(objects_dir), rm)


def test_space_loader_schema_validation(tmp_path):
    spaces_dir = tmp_path / "spaces"
    spaces_dir.mkdir()
    (spaces_dir / "invalid.yaml").write_text(
        textwrap.dedent(
            """
            spaces:
              - id: faulty_space
                name: Faulty
            """
        ),
        encoding="utf-8",
    )

    rm = RegistryManager()

    with pytest.raises(LoaderError):
        load_spaces(str(spaces_dir), rm)
