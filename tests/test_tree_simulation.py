"""
Unit tests for tree-based simulation system.

Tests cover:
- TreeSimulationRunner execution
- SimulationTree structure
- TreeNode creation
- WorldSnapshot handling
- Precondition evaluation
- Effect application
- History serialization
"""

from pathlib import Path

import pytest
import yaml

from simulator.cli.paths import kb_actions_path, kb_objects_path, kb_spaces_path
from simulator.core.registries import RegistryManager
from simulator.core.tree.models import (
    BranchCondition,
    SimulationTree,
    TreeNode,
    WorldSnapshot,
)
from simulator.core.tree.tree_runner import TreeSimulationRunner
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _load_test_registries() -> RegistryManager:
    """Load all registries for testing."""
    rm = RegistryManager()
    load_spaces(kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(kb_objects_path(None), rm)
    load_actions(kb_actions_path(None), rm)
    return rm


@pytest.fixture(scope="module")
def registry_manager() -> RegistryManager:
    """Load registries once for all tests."""
    return _load_test_registries()


class TestWorldSnapshot:
    """Tests for WorldSnapshot model."""

    def test_world_snapshot_creation(self):
        """WorldSnapshot can be created with object state."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(
            type="test_object",
            parts={},
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        assert snapshot.object_state.type == "test_object"
        assert snapshot.timestamp  # Should have default timestamp

    def test_world_snapshot_timestamp_format(self):
        """Timestamp should be in YYYY-MM-DD format."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        # Should match YYYY-MM-DD format
        import re

        assert re.match(r"\d{4}-\d{2}-\d{2}", snapshot.timestamp)


class TestTreeNode:
    """Tests for TreeNode model."""

    def test_tree_node_creation(self):
        """TreeNode can be created with required fields."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        node = TreeNode(
            id="state0",
            snapshot=snapshot,
        )

        assert node.id == "state0"
        assert node.parent_id is None
        assert node.children_ids == []
        assert node.action_name is None
        assert node.action_status == "ok"

    def test_tree_node_with_action(self):
        """TreeNode tracks action information."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        node = TreeNode(
            id="state1",
            snapshot=snapshot,
            parent_id="state0",
            action_name="turn_on",
            action_parameters={"level": "high"},
            action_status="ok",
        )

        assert node.action_name == "turn_on"
        assert node.action_parameters == {"level": "high"}
        assert node.parent_id == "state0"


class TestBranchCondition:
    """Tests for BranchCondition model."""

    def test_branch_condition_creation(self):
        """BranchCondition stores condition information."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="equals",
            value="high",
            source="precondition",
        )

        assert cond.attribute == "battery.level"
        assert cond.operator == "equals"
        assert cond.value == "high"
        assert cond.source == "precondition"


class TestSimulationTree:
    """Tests for SimulationTree model."""

    def test_simulation_tree_creation(self):
        """SimulationTree can be created with root node."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="flashlight", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)
        root = TreeNode(id="state0", snapshot=snapshot)

        tree = SimulationTree(
            simulation_id="test_sim",
            object_type="flashlight",
            object_name="flashlight",
            root_id="state0",
            nodes={"state0": root},
            current_path=["state0"],
        )

        assert tree.simulation_id == "test_sim"
        assert tree.object_type == "flashlight"
        assert tree.root_id == "state0"
        assert len(tree.nodes) == 1
        assert tree.current_path == ["state0"]


class TestTreeSimulationRunner:
    """Tests for TreeSimulationRunner."""

    def test_runner_initialization(self, registry_manager):
        """Runner initializes with registry manager."""
        runner = TreeSimulationRunner(registry_manager)

        assert runner.registry_manager is registry_manager
        assert runner.engine is not None

    def test_simple_simulation(self, registry_manager):
        """Run simple flashlight turn_on simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions, simulation_id="test_simple")

        assert tree.simulation_id == "test_simple"
        assert tree.object_type == "flashlight"
        assert len(tree.nodes) == 2  # root + turn_on result
        assert tree.current_path == ["state0", "state1"]

    def test_multi_action_simulation(self, registry_manager):
        """Run multi-action simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_multi")

        assert len(tree.nodes) == 3  # root + turn_on + turn_off
        assert tree.current_path == ["state0", "state1", "state2"]

        # Verify parent-child relationships
        root = tree.nodes["state0"]
        assert "state1" in root.children_ids

        state1 = tree.nodes["state1"]
        assert state1.parent_id == "state0"
        assert state1.action_name == "turn_on"
        assert "state2" in state1.children_ids

        state2 = tree.nodes["state2"]
        assert state2.parent_id == "state1"
        assert state2.action_name == "turn_off"

    def test_node_ids_sequential(self, registry_manager):
        """Node IDs should be sequential state0, state1, etc."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        expected_ids = ["state0", "state1", "state2", "state3"]
        assert tree.current_path == expected_ids
        for node_id in expected_ids:
            assert node_id in tree.nodes

    def test_precondition_failure(self, registry_manager):
        """Action with failed precondition creates error node."""
        runner = TreeSimulationRunner(registry_manager)
        # drain_battery then turn_on - turn_on requires battery not empty
        actions = [
            {"name": "drain_battery", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="test_fail")

        assert len(tree.nodes) == 3
        state2 = tree.nodes["state2"]
        assert state2.action_name == "turn_on"
        assert state2.action_status == "rejected"
        assert state2.action_error is not None

    def test_changes_recorded(self, registry_manager):
        """Changes are recorded in nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        state1 = tree.nodes["state1"]
        assert len(state1.changes) > 0

        # Should have changes for switch.position and bulb.state at minimum
        change_attrs = [c["attribute"] for c in state1.changes]
        assert "switch.position" in change_attrs
        assert "bulb.state" in change_attrs

    def test_tv_simulation(self, registry_manager):
        """Test TV object simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_tv")

        assert tree.object_type == "tv"
        assert len(tree.nodes) == 3

    def test_action_with_parameters(self, registry_manager):
        """Test action with parameters."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
        ]

        tree = runner.run("tv", actions, simulation_id="test_params")

        state2 = tree.nodes["state2"]
        assert state2.action_name == "adjust_volume"
        assert state2.action_parameters == {"level": "high"}


class TestTreeSerialization:
    """Tests for tree serialization to YAML."""

    def test_tree_to_yaml(self, registry_manager):
        """Tree can be serialized to YAML."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        tree_dict = tree.model_dump()

        # Should be serializable to YAML
        yaml_str = yaml.dump(tree_dict, default_flow_style=False)
        assert yaml_str is not None
        assert "simulation_id" in yaml_str
        assert "state0" in yaml_str

    def test_tree_from_yaml(self, registry_manager):
        """Tree can be deserialized from YAML."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        original = runner.run("flashlight", actions, simulation_id="test_yaml")
        tree_dict = original.model_dump()

        # Round-trip through YAML
        yaml_str = yaml.dump(tree_dict)
        loaded_dict = yaml.safe_load(yaml_str)
        restored = SimulationTree.model_validate(loaded_dict)

        assert restored.simulation_id == original.simulation_id
        assert restored.object_type == original.object_type
        assert len(restored.nodes) == len(original.nodes)
        assert restored.current_path == original.current_path


class TestVisualization:
    """Tests for HTML visualization generation."""

    def test_visualization_generation(self, registry_manager, tmp_path):
        """Visualization can be generated from tree."""
        from simulator.visualizer.generator import generate_html

        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        tree_dict = tree.model_dump()

        output_path = tmp_path / "test_viz.html"
        generate_html(tree_dict, str(output_path))

        assert output_path.exists()
        content = output_path.read_text()
        assert "Simulation Tree" in content
        assert "state0" in content
        assert "flashlight" in content

    def test_visualization_from_yaml(self, registry_manager, tmp_path):
        """Visualization can be generated from YAML file."""
        from simulator.visualizer.generator import generate_visualization

        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # Save to YAML
        yaml_path = tmp_path / "test_history.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(tree.model_dump(), f)

        # Generate visualization
        html_path = generate_visualization(str(yaml_path))

        assert Path(html_path).exists()
        assert html_path.endswith("_visualization.html")


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_flashlight_cycle(self, registry_manager):
        """Full flashlight simulation cycle."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions, simulation_id="flashlight_cycle")

        # With value sets from trends, we get branching:
        # turn_on creates value set {empty, low, medium}
        # turn_off preserves it
        # second turn_on branches: success path ({low, medium}) and fail path (empty)
        # This results in 6+ nodes instead of 5
        assert len(tree.nodes) >= 5
        # Main path should all be successful
        assert all(tree.nodes[nid].action_status == "ok" for nid in tree.current_path)

    def test_full_tv_session(self, registry_manager):
        """Full TV session simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "open_streaming", "parameters": {}},
            {"name": "adjust_volume", "parameters": {"level": "high"}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("tv", actions, simulation_id="tv_session")

        assert tree.object_type == "tv"
        assert len(tree.nodes) == 5

    def test_kettle_workflow(self, registry_manager):
        """Kettle workflow simulation."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "pour_water", "parameters": {"level": "full"}},
            {"name": "heat", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("kettle", actions, simulation_id="kettle_workflow")

        assert tree.object_type == "kettle"
        # Some actions may fail due to preconditions, that's expected
        assert len(tree.nodes) >= 2


class TestTreeStatistics:
    """Tests for tree statistics (Phase 2 ready)."""

    def test_get_statistics(self, registry_manager):
        """Tree provides comprehensive statistics."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)
        stats = tree.get_statistics()

        assert "total_nodes" in stats
        assert "depth" in stats
        assert "width" in stats
        assert "leaf_nodes" in stats
        assert "branch_points" in stats
        assert "successful_actions" in stats
        assert "failed_actions" in stats
        assert "path_length" in stats

        assert stats["total_nodes"] == 3
        assert stats["depth"] == 3
        assert stats["successful_actions"] == 2
        assert stats["failed_actions"] == 0

    def test_get_leaf_nodes(self, registry_manager):
        """Tree can identify leaf nodes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        leaves = tree.get_leaf_nodes()

        assert len(leaves) == 1
        assert leaves[0].id == "state1"

    def test_get_path_to_node(self, registry_manager):
        """Tree can reconstruct path to any node."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)
        path = tree.get_path_to_node("state2")

        assert len(path) == 3
        assert path[0].id == "state0"
        assert path[1].id == "state1"
        assert path[2].id == "state2"


class TestWorldSnapshotMethods:
    """Tests for WorldSnapshot helper methods (Phase 2 ready)."""

    def test_get_attribute_value(self, registry_manager):
        """WorldSnapshot provides attribute access."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)
        snapshot = tree.nodes["state1"].snapshot

        # Part attribute
        value = snapshot.get_attribute_value("switch.position")
        assert value == "on"

    def test_get_all_attribute_paths(self, registry_manager):
        """WorldSnapshot lists all attribute paths."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        snapshot = tree.root.snapshot
        paths = snapshot.get_all_attribute_paths()

        assert "switch.position" in paths
        assert "battery.level" in paths
        assert "bulb.state" in paths

    def test_is_attribute_known(self, registry_manager):
        """WorldSnapshot can check if attribute is known."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        snapshot = tree.root.snapshot

        # All attributes should be known in Phase 1
        assert snapshot.is_attribute_known("battery.level")
        assert snapshot.is_attribute_known("switch.position")


class TestTreeNodeProperties:
    """Tests for TreeNode properties (Phase 2 ready)."""

    def test_node_succeeded_property(self, registry_manager):
        """TreeNode has succeeded property."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        assert tree.nodes["state1"].succeeded is True
        assert tree.nodes["state1"].failed is False

    def test_node_failed_property(self, registry_manager):
        """TreeNode has failed property for rejected actions."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "drain_battery", "parameters": {}},
            {"name": "turn_on", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        # state2 should be rejected (empty battery)
        assert tree.nodes["state2"].failed is True
        assert tree.nodes["state2"].succeeded is False

    def test_node_change_count(self, registry_manager):
        """TreeNode tracks change count."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        assert tree.nodes["state0"].change_count == 0  # Root has no changes
        assert tree.nodes["state1"].change_count > 0  # turn_on has changes

    def test_node_get_changed_attributes(self, registry_manager):
        """TreeNode can list changed attributes."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        changed = tree.nodes["state1"].get_changed_attributes()
        assert "switch.position" in changed
        assert "bulb.state" in changed


class TestCLIMetadata:
    """Tests for CLI command metadata in tree."""

    def test_tree_stores_actions_list(self, registry_manager):
        """Tree stores list of actions executed."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [
            {"name": "turn_on", "parameters": {}},
            {"name": "turn_off", "parameters": {}},
        ]

        tree = runner.run("flashlight", actions)

        # CLI command is set by CLI, not runner
        # But actions list should be empty by default (set by CLI)
        assert tree.actions == []  # Not set by runner

    def test_tree_cli_command_default(self, registry_manager):
        """Tree CLI command is None by default."""
        runner = TreeSimulationRunner(registry_manager)
        tree = runner.run("flashlight", [])

        assert tree.cli_command is None  # Set by CLI, not runner


# =============================================================================
# Phase 2: Branching Tests
# =============================================================================


class TestAttributeSnapshotValueSets:
    """Tests for AttributeSnapshot value set support."""

    def test_single_value(self):
        """AttributeSnapshot handles single value."""
        from simulator.core.simulation_runner import AttributeSnapshot

        attr = AttributeSnapshot(value="high", trend=None)

        assert attr.value == "high"
        assert attr.is_value_set() is False
        assert attr.get_single_value() == "high"
        assert attr.get_value_as_set() == {"high"}
        assert attr.is_unknown() is False

    def test_value_set(self):
        """AttributeSnapshot handles value sets (list)."""
        from simulator.core.simulation_runner import AttributeSnapshot

        attr = AttributeSnapshot(value=["low", "medium"], trend=None)

        assert attr.value == ["low", "medium"]
        assert attr.is_value_set() is True
        assert attr.get_single_value() == "low"  # First element
        assert attr.get_value_as_set() == {"low", "medium"}
        assert attr.is_unknown() is True  # Multiple values = unknown

    def test_none_value(self):
        """AttributeSnapshot handles None value."""
        from simulator.core.simulation_runner import AttributeSnapshot

        attr = AttributeSnapshot(value=None, trend=None)

        assert attr.value is None
        assert attr.is_value_set() is False
        assert attr.get_single_value() is None
        assert attr.get_value_as_set() == set()
        assert attr.is_unknown() is True

    def test_unknown_string_value(self):
        """AttributeSnapshot recognizes 'unknown' string."""
        from simulator.core.simulation_runner import AttributeSnapshot

        attr = AttributeSnapshot(value="unknown", trend=None)

        assert attr.is_unknown() is True

    def test_single_element_list(self):
        """Single-element list is considered known."""
        from simulator.core.simulation_runner import AttributeSnapshot

        attr = AttributeSnapshot(value=["high"], trend=None)

        assert attr.is_value_set() is True
        assert attr.is_unknown() is False  # Single element = known


class TestBranchConditionValueSets:
    """Tests for BranchCondition value set support."""

    def test_branch_condition_single_value(self):
        """BranchCondition with single value."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="equals",
            value="high",
            source="precondition",
            branch_type="success",
        )

        assert cond.is_value_set() is False
        assert cond.get_value_display() == "high"
        assert cond.matches_value("high") is True
        assert cond.matches_value("low") is False

    def test_branch_condition_value_set(self):
        """BranchCondition with value set (list)."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "empty"],
            source="postcondition",
            branch_type="else",
        )

        assert cond.is_value_set() is True
        assert cond.get_value_display() == "{low, empty}"
        assert cond.matches_value("low") is True
        assert cond.matches_value("empty") is True
        assert cond.matches_value("high") is False

    def test_branch_condition_describe_set(self):
        """BranchCondition describe() handles value sets."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "empty"],
            source="postcondition",
            branch_type="else",
        )

        desc = cond.describe()
        assert "battery.level" in desc
        assert "{low, empty}" in desc


class TestValueSetFromTrend:
    """Tests for computing value sets from trends."""

    def test_trend_down_from_high(self, registry_manager):
        """Trend down from high gives values at or below."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("high", "down", "generic_level")

        # generic_level: ["empty", "low", "medium", "high", "full"]
        # down from high: empty, low, medium, high
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" not in values

    def test_trend_down_from_medium(self, registry_manager):
        """Trend down from medium gives values at or below."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("medium", "down", "generic_level")

        # down from medium: empty, low, medium
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" not in values
        assert "full" not in values

    def test_trend_up_from_low(self, registry_manager):
        """Trend up from low gives values at or above."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("low", "up", "generic_level")

        # up from low: low, medium, high, full
        assert "empty" not in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" in values

    def test_trend_none(self, registry_manager):
        """No trend keeps current value only."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("medium", "none", "generic_level")

        assert values == ["medium"]

    def test_trend_invalid_value(self, registry_manager):
        """Invalid current value returns itself."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("invalid", "down", "generic_level")

        assert values == ["invalid"]

    def test_trend_invalid_space(self, registry_manager):
        """Invalid space returns current value."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._compute_value_set_from_trend("medium", "down", "nonexistent_space")

        assert values == ["medium"]


class TestWorldSnapshotValueSets:
    """Tests for WorldSnapshot handling value sets."""

    def test_get_attribute_value_with_set(self):
        """WorldSnapshot returns value set from attribute."""
        from simulator.core.simulation_runner import (
            AttributeSnapshot,
            ObjectStateSnapshot,
            PartStateSnapshot,
        )

        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend="down")}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        value = snapshot.get_attribute_value("battery.level")
        assert value == ["low", "medium"]

    def test_is_attribute_known_with_set(self):
        """WorldSnapshot detects value sets as unknown."""
        from simulator.core.simulation_runner import (
            AttributeSnapshot,
            ObjectStateSnapshot,
            PartStateSnapshot,
        )

        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend=None)}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        # Multiple values = unknown
        assert snapshot.is_attribute_known("battery.level") is False

    def test_is_attribute_value_set(self):
        """WorldSnapshot can check if value is a set."""
        from simulator.core.simulation_runner import (
            AttributeSnapshot,
            ObjectStateSnapshot,
            PartStateSnapshot,
        )

        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend=None)}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        assert snapshot.is_attribute_value_set("battery.level") is True


class TestPreconditionBranchingHelpers:
    """Tests for precondition branching helper methods."""

    def test_get_attribute_space_id(self, registry_manager):
        """Runner can get space ID for attribute."""
        runner = TreeSimulationRunner(registry_manager)

        # Create flashlight instance
        obj_type = registry_manager.objects.get("flashlight")
        from simulator.io.loaders.object_loader import instantiate_default

        instance = instantiate_default(obj_type, registry_manager)

        space_id = runner._get_attribute_space_id(instance, "battery.level")
        # Actual space ID from flashlight.yaml
        assert space_id == "battery_level"

    def test_get_all_space_values(self, registry_manager):
        """Runner can get all values in a space."""
        runner = TreeSimulationRunner(registry_manager)

        values = runner._get_all_space_values("generic_level")

        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" in values

    def test_evaluate_condition_for_value_equals(self, registry_manager):
        """Runner can evaluate condition for specific value."""
        runner = TreeSimulationRunner(registry_manager)

        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.objects.part import AttributeTarget

        condition = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="equals",
            value="high",
        )

        assert runner._evaluate_condition_for_value(condition, "high") is True
        assert runner._evaluate_condition_for_value(condition, "low") is False

    def test_evaluate_condition_for_value_not_equals(self, registry_manager):
        """Runner evaluates not_equals condition."""
        runner = TreeSimulationRunner(registry_manager)

        from simulator.core.actions.conditions.attribute_conditions import (
            AttributeCondition,
        )
        from simulator.core.objects.part import AttributeTarget

        condition = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )

        assert runner._evaluate_condition_for_value(condition, "empty") is False
        assert runner._evaluate_condition_for_value(condition, "high") is True


class TestBranchingIntegration:
    """Integration tests for branching (Phase 2)."""

    def test_linear_execution_with_known_values(self, registry_manager):
        """With all known values, execution is still linear."""
        runner = TreeSimulationRunner(registry_manager)
        actions = [{"name": "turn_on", "parameters": {}}]

        tree = runner.run("flashlight", actions)

        # Should be linear - 2 nodes (root + action result)
        assert len(tree.nodes) == 2
        assert tree.current_path == ["state0", "state1"]

    def test_tree_supports_multiple_children(self, registry_manager):
        """Tree structure supports nodes with multiple children."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        # Manually create a tree with branching
        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        tree = SimulationTree(
            simulation_id="test_branch",
            object_type="test",
            object_name="test",
        )

        # Create root
        root = TreeNode(id=tree.generate_node_id(), snapshot=snapshot)
        tree.add_node(root)

        # Create two children (simulating branching)
        child1 = TreeNode(
            id=tree.generate_node_id(),
            snapshot=snapshot,
            parent_id=root.id,
            action_name="action1",
            branch_condition=BranchCondition(
                attribute="test.attr",
                operator="equals",
                value="value1",
                source="precondition",
                branch_type="success",
            ),
        )

        child2 = TreeNode(
            id=tree.generate_node_id(),
            snapshot=snapshot,
            parent_id=root.id,
            action_name="action1",
            branch_condition=BranchCondition(
                attribute="test.attr",
                operator="in",
                value=["value2", "value3"],
                source="precondition",
                branch_type="fail",
            ),
        )

        tree.add_branch_nodes(root.id, [child1, child2])

        # Verify structure
        assert len(root.children_ids) == 2
        assert "state1" in root.children_ids
        assert "state2" in root.children_ids
        assert tree.count_branches() == 1

    def test_tree_get_siblings(self, registry_manager):
        """Tree can get siblings of a node."""
        from simulator.core.simulation_runner import ObjectStateSnapshot

        obj_state = ObjectStateSnapshot(type="test", parts={}, global_attributes={})
        snapshot = WorldSnapshot(object_state=obj_state)

        tree = SimulationTree(
            simulation_id="test_siblings",
            object_type="test",
            object_name="test",
        )

        root = TreeNode(id=tree.generate_node_id(), snapshot=snapshot)
        tree.add_node(root)

        child1 = TreeNode(id=tree.generate_node_id(), snapshot=snapshot, parent_id=root.id)
        child2 = TreeNode(id=tree.generate_node_id(), snapshot=snapshot, parent_id=root.id)
        tree.add_branch_nodes(root.id, [child1, child2])

        siblings = tree.get_siblings("state1")
        assert len(siblings) == 1
        assert siblings[0].id == "state2"


class TestVisualizationValueSets:
    """Tests for visualization with value sets."""

    def test_visualization_handles_value_sets(self, registry_manager, tmp_path):
        """Visualization correctly displays value sets."""
        from simulator.visualizer.generator import generate_html

        # Create tree data with value sets
        tree_data = {
            "simulation_id": "test_value_sets",
            "object_type": "flashlight",
            "object_name": "flashlight",
            "created_at": "2025-01-01",
            "root_id": "state0",
            "current_path": ["state0", "state1"],
            "nodes": {
                "state0": {
                    "id": "state0",
                    "snapshot": {
                        "object_state": {
                            "type": "flashlight",
                            "parts": {
                                "battery": {
                                    "attributes": {
                                        "level": {
                                            "value": ["low", "medium"],  # Value set
                                            "trend": "down",
                                        }
                                    }
                                }
                            },
                            "global_attributes": {},
                        },
                        "timestamp": "2025-01-01",
                    },
                    "parent_id": None,
                    "children_ids": ["state1"],
                    "action_name": None,
                    "action_parameters": {},
                    "action_status": "ok",
                    "changes": [],
                },
                "state1": {
                    "id": "state1",
                    "snapshot": {
                        "object_state": {
                            "type": "flashlight",
                            "parts": {"battery": {"attributes": {"level": {"value": "low", "trend": None}}}},
                            "global_attributes": {},
                        },
                        "timestamp": "2025-01-01",
                    },
                    "parent_id": "state0",
                    "children_ids": [],
                    "action_name": "turn_on",
                    "action_parameters": {},
                    "action_status": "ok",
                    "branch_condition": {
                        "attribute": "battery.level",
                        "operator": "in",
                        "value": ["low", "medium"],
                        "source": "postcondition",
                        "branch_type": "else",
                    },
                    "changes": [],
                },
            },
        }

        output_path = tmp_path / "test_value_sets.html"
        html = generate_html(tree_data, str(output_path))

        assert output_path.exists()
        assert "formatValue" in html  # JS function for formatting
        assert "value-set" in html  # CSS class for value sets


class TestCombinedBranching:
    """Tests for combined precondition + postcondition branching (Phase 2 refined)."""

    def test_combined_branching_same_attribute(self, registry_manager):
        """
        When precondition and postcondition check same attribute,
        each postcondition case creates a separate branch.
        """
        runner = TreeSimulationRunner(registry_manager)

        # Set battery.level to unknown to trigger branching
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="combined_same_attr",
            initial_values={"battery.level": "unknown"},
        )

        # With flat if-elif structure (full/high/medium/low), should have 6 nodes:
        # - state0: root
        # - state1-4: success branches (full, high, medium, low)
        # - state5: fail (precondition fail with empty)
        assert len(tree.nodes) == 6

        # Check that we have success branches first, then fail branch
        success_nodes = [n for n in tree.nodes.values() if n.action_status == "ok" and n.action_name]
        fail_nodes = [n for n in tree.nodes.values() if n.action_status == "rejected"]

        assert len(success_nodes) == 4  # Four postcondition branches (full, high, medium, low)
        assert len(fail_nodes) == 1  # One fail branch

        # Verify fail node has empty as its value
        fail_node = fail_nodes[0]
        assert fail_node.branch_condition is not None
        assert fail_node.branch_condition.value == "empty"
        assert fail_node.branch_condition.branch_type == "fail"

    def test_combined_branching_success_branches_first(self, registry_manager):
        """Success branches should be created before fail branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="success_first",
            initial_values={"battery.level": "unknown"},
        )

        # Get children of root (state0)
        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # First child should be success (ok status)
        if len(children) > 0:
            first_child = children[0]
            assert first_child.action_status == "ok"

    def test_combined_branching_each_value_separate(self, registry_manager):
        """
        With flat if-elif structure, each value gets its own branch
        with correct effects applied.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="each_value_test",
            initial_values={"battery.level": "unknown"},
        )

        # Collect all postcondition branches
        postcond_branches = [
            n for n in tree.nodes.values() if n.branch_condition and n.branch_condition.source == "postcondition"
        ]

        # Should have 4 branches: full, high, medium, low
        assert len(postcond_branches) == 4

        # Each value should have its own branch
        branch_values = {n.branch_condition.value for n in postcond_branches}
        assert branch_values == {"full", "high", "medium", "low"}

    def test_branches_continue_to_next_action(self, registry_manager):
        """All branches (including fail) should continue to subsequent actions."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "flashlight",
            [
                {"name": "turn_on", "parameters": {}},
                {"name": "turn_off", "parameters": {}},
            ],
            simulation_id="branches_continue",
            initial_values={"battery.level": "unknown"},
        )

        # After turn_on with unknown battery:
        # - 4 success branches (full, high, medium, low)
        # - 1 fail branch (empty)
        # After turn_off applied to all 5:
        # - Should have 5 turn_off nodes
        # Total: 1 (root) + 5 (turn_on branches) + 5 (turn_off from each branch) = 11

        turn_off_nodes = [n for n in tree.nodes.values() if n.action_name == "turn_off"]
        assert len(turn_off_nodes) == 5, "turn_off should be applied to all 5 branches"

    def test_linear_when_values_known(self, registry_manager):
        """When values are known, no branching occurs."""
        runner = TreeSimulationRunner(registry_manager)

        # Default battery.level is 'medium' (known value)
        tree = runner.run(
            "flashlight",
            [{"name": "turn_on", "parameters": {}}],
            simulation_id="linear_known",
        )

        # Should be linear: root + turn_on result = 2 nodes
        assert len(tree.nodes) == 2
        assert len(tree.current_path) == 2


class TestInOperatorBranching:
    """Tests for the 'in' operator in postcondition branching."""

    def test_in_operator_groups_values_as_set(self, registry_manager):
        """Values matched by 'in' operator should be grouped as a value set."""
        runner = TreeSimulationRunner(registry_manager)

        # dice uses 'in' operator for else colors: yellow, black, white
        tree = runner.run(
            "dice",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_operator_test",
            initial_values={"cube.face": "unknown", "cube.color": "unknown"},
        )

        # Should have 5 nodes: root + 4 branches (green, red, {yellow,black,white}, fail)
        assert len(tree.nodes) == 5

        # Find the branch with the value set (grouped colors)
        grouped_branch = None
        for node in tree.nodes.values():
            if node.branch_condition:
                val = node.branch_condition.value
                if isinstance(val, list) and len(val) == 3:
                    grouped_branch = node
                    break

        assert grouped_branch is not None, "Should have a branch with grouped values"
        assert set(grouped_branch.branch_condition.value) == {"yellow", "black", "white"}

    def test_in_operator_precondition_with_unknown(self, registry_manager):
        """Precondition with 'in' operator should create fail branch for excluded values."""
        runner = TreeSimulationRunner(registry_manager)

        # dice_same_attr: precondition is face IN {3, 5, 6}
        tree = runner.run(
            "dice_same_attr",
            [{"name": "check_win", "parameters": {}}],
            simulation_id="in_precond_test",
            initial_values={"cube.face": "unknown"},
        )

        # Should have fail branch with face={1, 2, 4}
        fail_nodes = [n for n in tree.nodes.values() if n.action_status == "rejected"]
        assert len(fail_nodes) == 1

        fail_face = fail_nodes[0].snapshot.get_attribute_value("cube.face")
        assert set(fail_face) == {"1", "2", "4"}, f"Expected fail with {{1,2,4}}, got {fail_face}"
