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
            parent_ids=["state0"],
            action_name="turn_on",
            action_parameters={"level": "high"},
            action_status="ok",
        )

        assert node.action_name == "turn_on"
        assert node.action_parameters == {"level": "high"}
        assert node.parent_id == "state0"  # backward-compatible property


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
        # turn_off now requires switch.position == "on" precondition
        # This results in branching with some success and some fail paths
        assert len(tree.nodes) >= 5
        # At least some successful nodes exist
        successful_nodes = [n for n in tree.nodes.values() if n.action_status == "ok"]
        assert len(successful_nodes) >= 3  # root + at least some successes

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
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("high", "down", "generic_level", registry_manager)

        # generic_level: ["empty", "low", "medium", "high", "full"]
        # down from high: empty, low, medium, high
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" not in values

    def test_trend_down_from_medium(self, registry_manager):
        """Trend down from medium gives values at or below."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "down", "generic_level", registry_manager)

        # down from medium: empty, low, medium
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" not in values
        assert "full" not in values

    def test_trend_up_from_low(self, registry_manager):
        """Trend up from low gives values at or above."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("low", "up", "generic_level", registry_manager)

        # up from low: low, medium, high, full
        assert "empty" not in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" in values

    def test_trend_none(self, registry_manager):
        """No trend keeps current value only."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "none", "generic_level", registry_manager)

        assert values == ["medium"]

    def test_trend_invalid_value(self, registry_manager):
        """Invalid current value returns itself."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("invalid", "down", "generic_level", registry_manager)

        assert values == ["invalid"]

    def test_trend_invalid_space(self, registry_manager):
        """Invalid space returns current value."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "down", "nonexistent_space", registry_manager)

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
        """Can get space ID for attribute."""
        from simulator.core.tree.snapshot_utils import get_attribute_space_id

        # Create flashlight instance
        obj_type = registry_manager.objects.get("flashlight")
        from simulator.io.loaders.object_loader import instantiate_default

        instance = instantiate_default(obj_type, registry_manager)

        space_id = get_attribute_space_id(instance, "battery.level")
        # Actual space ID from flashlight.yaml
        assert space_id == "battery_level"

    def test_get_all_space_values(self, registry_manager):
        """Can get all values in a space."""
        from simulator.core.tree.snapshot_utils import get_all_space_values

        values = get_all_space_values("generic_level", registry_manager)

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

        # With flat if-elif structure ({full,high}/medium/low), should have 5 nodes:
        # - state0: root
        # - state1-3: success branches ({full,high}, medium, low)
        # - state4: fail (precondition fail with empty)
        assert len(tree.nodes) == 5

        # Check that we have success branches first, then fail branch
        success_nodes = [n for n in tree.nodes.values() if n.action_status == "ok" and n.action_name]
        fail_nodes = [n for n in tree.nodes.values() if n.action_status == "rejected"]

        assert len(success_nodes) == 3  # Three postcondition branches ({full,high}, medium, low)
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
        With flat if-elif structure, each condition gets its own branch
        with correct effects applied. {full, high} are combined via 'in' operator.
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

        # Should have 3 branches: {full,high}, medium, low
        assert len(postcond_branches) == 3

        # Check that we have the expected branch values
        # One branch should have a list value (from 'in' operator)
        list_branches = [n for n in postcond_branches if isinstance(n.branch_condition.value, list)]
        assert len(list_branches) == 1
        assert set(list_branches[0].branch_condition.value) == {"full", "high"}

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
        # - 3 success branches ({full,high}, medium, low)
        # - 1 fail branch (empty)
        # After turn_off applied to all 4:
        # - Should have 4 turn_off nodes

        turn_off_nodes = [n for n in tree.nodes.values() if n.action_name == "turn_off"]
        assert len(turn_off_nodes) == 4, "turn_off should be applied to all 4 branches"

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


class TestComparisonOperators:
    """Tests for comparison operators (>=, <=, >, <) in conditions."""

    def test_gte_operator_expands_to_value_set(self):
        """The >= operator should expand to all values at or above the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level >= low means {low, medium, high, full}
        result = space.get_values_for_comparison("low", "gte")
        assert result == ["low", "medium", "high", "full"]

    def test_lte_operator_expands_to_value_set(self):
        """The <= operator should expand to all values at or below the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level <= medium means {empty, low, medium}
        result = space.get_values_for_comparison("medium", "lte")
        assert result == ["empty", "low", "medium"]

    def test_gt_operator_excludes_threshold(self):
        """The > operator should expand to values strictly above the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level > medium means {high, full}
        result = space.get_values_for_comparison("medium", "gt")
        assert result == ["high", "full"]

    def test_lt_operator_excludes_threshold(self):
        """The < operator should expand to values strictly below the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level < medium means {empty, low}
        result = space.get_values_for_comparison("medium", "lt")
        assert result == ["empty", "low"]

    def test_edge_case_gte_at_first_level(self):
        """gte at the first level should return all levels."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        result = space.get_values_for_comparison("empty", "gte")
        assert result == ["empty", "low", "medium", "high", "full"]

    def test_edge_case_lt_at_first_level(self):
        """lt at the first level should return empty list."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        result = space.get_values_for_comparison("empty", "lt")
        assert result == []


class TestAndCondition:
    """Tests for AND compound conditions."""

    def test_and_condition_creation(self):
        """AndCondition can be created with multiple sub-conditions."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="off",
        )

        and_cond = AndCondition(conditions=[cond1, cond2])

        assert len(and_cond.conditions) == 2
        assert and_cond.describe() == "(battery.level != empty AND switch.position == off)"

    def test_and_condition_get_checked_attributes(self):
        """AndCondition.get_checked_attributes returns all attribute paths."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="off",
        )

        and_cond = AndCondition(conditions=[cond1, cond2])
        attrs = and_cond.get_checked_attributes()

        assert "battery.level" in attrs
        assert "switch.position" in attrs

    def test_and_condition_parsing_from_yaml(self):
        """AND conditions can be parsed from YAML spec."""
        from simulator.core.actions.specs import build_condition, parse_condition_spec

        yaml_data = {
            "type": "and",
            "conditions": [
                {"type": "attribute_check", "target": "battery.level", "operator": "not_equals", "value": "empty"},
                {"type": "attribute_check", "target": "switch.position", "operator": "equals", "value": "off"},
            ],
        }

        spec = parse_condition_spec(yaml_data)
        condition = build_condition(spec)

        from simulator.core.actions.conditions.logical_conditions import AndCondition

        assert isinstance(condition, AndCondition)
        assert len(condition.conditions) == 2

    def test_branch_condition_compound_type(self):
        """BranchCondition supports compound_type for AND conditions."""
        from simulator.core.tree.models import BranchCondition

        sub1 = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "medium", "high", "full"],
            source="precondition",
            branch_type="success",
        )
        sub2 = BranchCondition(
            attribute="switch.position",
            operator="equals",
            value="off",
            source="precondition",
            branch_type="success",
        )

        compound = BranchCondition(
            attribute="",
            operator="",
            value="",
            source="precondition",
            branch_type="success",
            compound_type="and",
            sub_conditions=[sub1, sub2],
        )

        assert compound.is_compound()
        assert compound.compound_type == "and"
        assert len(compound.sub_conditions) == 2
        # Check the description contains the expected parts
        desc = compound.describe()
        assert "battery.level" in desc
        assert "switch.position" in desc
        assert "AND" in desc


class TestOrCondition:
    """Tests for OR compound conditions."""

    def test_or_condition_creation(self):
        """OrCondition can be created with multiple sub-conditions."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import OrCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="equals",
            value="full",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="on",
        )

        or_cond = OrCondition(conditions=[cond1, cond2])

        assert len(or_cond.conditions) == 2
        assert or_cond.describe() == "(battery.level == full OR switch.position == on)"

    def test_or_condition_parsing_from_yaml(self):
        """OR conditions can be parsed from YAML spec."""
        from simulator.core.actions.specs import build_condition, parse_condition_spec

        yaml_data = {
            "type": "or",
            "conditions": [
                {"type": "attribute_check", "target": "battery.level", "operator": "equals", "value": "full"},
                {"type": "attribute_check", "target": "switch.position", "operator": "equals", "value": "on"},
            ],
        }

        spec = parse_condition_spec(yaml_data)
        condition = build_condition(spec)

        from simulator.core.actions.conditions.logical_conditions import OrCondition

        assert isinstance(condition, OrCondition)
        assert len(condition.conditions) == 2


class TestDeMorganPreconditions:
    """Tests for De Morgan's law in preconditions.

    Uses real-world objects:
    - Coffee Machine: AND conditions (water >= low AND beans >= low AND temp == hot)
    - Slot Machine: OR conditions (reel1 == seven OR reel2 == seven OR reel3 == seven)

    Verifies:
    - AND precondition: 1 success branch + N fail branches (De Morgan: NOT(A AND B) = NOT(A) OR NOT(B))
    - OR precondition: N success branches + 1 fail branch (De Morgan: NOT(A OR B) = NOT(A) AND NOT(B))
    """

    def test_and_precondition_with_two_unknowns(self, registry_manager):
        """Slot machine: AND precondition (check_jackpot) with 3 unknowns.

        check_jackpot requires: reel1 == seven AND reel2 == seven AND reel3 == seven
        De Morgan: NOT(A AND B AND C) = NOT(A) OR NOT(B) OR NOT(C) → 3 fail branches
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_jackpot", "parameters": {}}],
            simulation_id="test_and_demorgan_precond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Count success and fail branches (rejected = precondition failed)
        success_branches = [c for c in children if c.action_status == "ok"]
        fail_branches = [c for c in children if c.action_status == "rejected"]

        assert len(success_branches) == 1, "Should have exactly 1 success branch"
        assert len(fail_branches) >= 3, "De Morgan: NOT(A AND B AND C) → at least 3 fail branches"

        # Verify success branch has all conditions satisfied
        success = success_branches[0]
        reel1 = success.snapshot.get_attribute_value("reel1.symbol")
        reel2 = success.snapshot.get_attribute_value("reel2.symbol")
        reel3 = success.snapshot.get_attribute_value("reel3.symbol")

        assert reel1 == "seven", "Success: reel1 should be 'seven'"
        assert reel2 == "seven", "Success: reel2 should be 'seven'"
        assert reel3 == "seven", "Success: reel3 should be 'seven'"

    def test_or_precondition_with_two_unknowns(self, registry_manager):
        """Slot machine: OR precondition with 2 unknown reels creates 2 success + 1 fail.

        check_any_seven requires: reel1 == seven OR reel2 == seven OR reel3 == seven
        Testing with 2 reels unknown.
        De Morgan: NOT(A OR B) = NOT(A) AND NOT(B) → 1 fail branch
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_or_demorgan_precond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "bar",  # Known, not seven
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        success_branches = [c for c in children if c.action_status == "ok"]
        fail_branches = [c for c in children if c.action_status == "rejected"]

        # With 2 unknown reels, we should have 2 success (one per reel showing seven) + 1 fail
        assert len(success_branches) >= 2, "Should have at least 2 success branches (one per satisfied disjunct)"
        assert len(fail_branches) == 1, "De Morgan: NOT(A OR B) = NOT(A) AND NOT(B) → 1 fail branch"

        # Verify fail branch has BOTH reels NOT showing seven (De Morgan AND)
        fail_node = fail_branches[0]
        reel1 = fail_node.snapshot.get_attribute_value("reel1.symbol")
        reel2 = fail_node.snapshot.get_attribute_value("reel2.symbol")

        # Both should NOT be 'seven'
        if isinstance(reel1, list):
            assert "seven" not in reel1, "Fail: reel1 should NOT contain 'seven'"
        else:
            assert reel1 != "seven", "Fail: reel1 should not be 'seven'"

        if isinstance(reel2, list):
            assert "seven" not in reel2, "Fail: reel2 should NOT contain 'seven'"
        else:
            assert reel2 != "seven", "Fail: reel2 should not be 'seven'"


class TestDeMorganPostconditions:
    """Tests for De Morgan's law in postconditions.

    Uses real-world objects:
    - Coffee Machine: AND postcondition (if water >= low AND temp == hot then ready = on)
    - Slot Machine: OR postcondition (if reel1 == seven OR reel2 == bar then prize = small)

    Verifies:
    - AND postcondition: 1 THEN branch + N ELSE branches (De Morgan)
    - OR postcondition: N THEN branches + 1 ELSE branch (De Morgan)
    """

    def test_and_postcondition_with_two_unknowns(self, registry_manager):
        """Coffee machine: AND postcondition creates 1 THEN + 2 ELSE branches (De Morgan).

        check_ready: if (water_tank.level >= low AND heater.temperature == hot) then status.ready = on
        De Morgan ELSE: NOT(A AND B) = NOT(A) OR NOT(B) → 2 else branches
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_and_demorgan_postcond",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Should have 3 branches: 1 THEN + 2 ELSE (De Morgan)
        assert len(children) == 3, f"Expected 3 branches, got {len(children)}"

        # Identify THEN and ELSE branches by branch_condition
        then_branches = []
        else_branches = []
        for child in children:
            bc = child.branch_condition
            if bc and bc.branch_type == "if":
                then_branches.append(child)
            elif bc and bc.branch_type == "else":
                else_branches.append(child)

        assert len(then_branches) == 1, "Should have exactly 1 THEN branch"
        assert len(else_branches) == 2, "De Morgan: NOT(A AND B) → 2 ELSE branches"

        # Verify THEN branch: both conditions met, effect applied
        then_node = then_branches[0]
        water = then_node.snapshot.get_attribute_value("water_tank.level")
        temp = then_node.snapshot.get_attribute_value("heater.temperature")
        ready = then_node.snapshot.get_attribute_value("status.ready")

        # Water should be >= low (not empty)
        if isinstance(water, list):
            assert "empty" not in water, "THEN: water should not include 'empty'"
        else:
            assert water != "empty", "THEN: water should not be 'empty'"
        assert temp == "hot", "THEN: heater.temperature should be 'hot'"
        assert ready == "on", "THEN: status.ready should be set to 'on'"

        # Verify ELSE branches: one condition fails each, effect NOT applied
        for else_node in else_branches:
            ready = else_node.snapshot.get_attribute_value("status.ready")
            assert ready == "off", "ELSE: status.ready should remain 'off'"

    def test_or_postcondition_with_two_unknowns(self, registry_manager):
        """Slot machine: OR postcondition creates 2 THEN + 1 ELSE branch (De Morgan).

        award_prize: if (reel1 == seven OR reel2 == bar) then prize = small
        De Morgan ELSE: NOT(A OR B) = NOT(A) AND NOT(B) → 1 else branch
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "award_prize", "parameters": {}}],
            simulation_id="test_or_demorgan_postcond",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        children = [tree.nodes[cid] for cid in root.children_ids]

        # Should have 3 branches: 2 THEN + 1 ELSE (De Morgan)
        assert len(children) == 3, f"Expected 3 branches, got {len(children)}"

        then_branches = []
        else_branches = []
        for child in children:
            bc = child.branch_condition
            if bc and bc.branch_type == "if":
                then_branches.append(child)
            elif bc and bc.branch_type == "else":
                else_branches.append(child)

        assert len(then_branches) == 2, "Should have 2 THEN branches (one per disjunct)"
        assert len(else_branches) == 1, "De Morgan: NOT(A OR B) → 1 ELSE branch"

        # Verify THEN branches: at least one condition met, effect applied
        for then_node in then_branches:
            prize = then_node.snapshot.get_attribute_value("display.prize")
            assert prize == "small", "THEN: display.prize should be 'small'"

        # Verify ELSE branch: BOTH conditions fail (De Morgan AND), effect NOT applied
        else_node = else_branches[0]
        reel1 = else_node.snapshot.get_attribute_value("reel1.symbol")
        reel2 = else_node.snapshot.get_attribute_value("reel2.symbol")
        prize = else_node.snapshot.get_attribute_value("display.prize")

        # reel1 should NOT be 'seven'
        if isinstance(reel1, list):
            assert "seven" not in reel1, "ELSE: reel1 should NOT contain 'seven'"
        else:
            assert reel1 != "seven", "ELSE: reel1 should not be 'seven'"

        # reel2 should NOT be 'bar'
        if isinstance(reel2, list):
            assert "bar" not in reel2, "ELSE: reel2 should NOT contain 'bar'"
        else:
            assert reel2 != "bar", "ELSE: reel2 should not be 'bar'"

        assert prize == "none", "ELSE: display.prize should remain 'none'"


class TestDeMorganComplex:
    """Tests for complex De Morgan scenarios with real-world objects."""

    def test_and_precondition_branch_values_are_correct(self, registry_manager):
        """Coffee machine: Verify AND fail branches contain correct complement values."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_and_values",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "hot",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Should have fail branches (De Morgan)
        assert len(fail_branches) >= 2, "Should have at least 2 fail branches for AND"

        # Each fail branch should have a branch condition
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None, "Fail branch should have a branch condition"

    def test_or_precondition_fail_branch_has_all_complements(self, registry_manager):
        """Slot machine: Verify OR fail branch constrains ALL reels to complements."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_or_fail_values",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "bar",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_branches) == 1, "Should have exactly 1 fail branch for OR"

        fail = fail_branches[0]
        reel1 = fail.snapshot.get_attribute_value("reel1.symbol")
        reel2 = fail.snapshot.get_attribute_value("reel2.symbol")

        # Both reels should NOT be 'seven' (De Morgan AND)
        if isinstance(reel1, list):
            assert "seven" not in reel1, "OR fail: reel1 must not contain 'seven'"
        else:
            assert reel1 != "seven", "OR fail: reel1 must not be 'seven'"

        if isinstance(reel2, list):
            assert "seven" not in reel2, "OR fail: reel2 must not contain 'seven'"
        else:
            assert reel2 != "seven", "OR fail: reel2 must not be 'seven'"

    def test_postcondition_else_branch_effects_not_applied(self, registry_manager):
        """Coffee machine: Verify ELSE branches don't apply the conditional effects."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_else_no_effect",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]

        for cid in root.children_ids:
            child = tree.nodes[cid]
            bc = child.branch_condition

            if bc and bc.branch_type == "else":
                # ELSE branches should NOT have status.ready set to 'on'
                ready = child.snapshot.get_attribute_value("status.ready")
                assert ready == "off", f"ELSE branch should not apply effect: ready={ready}"
            elif bc and bc.branch_type == "if":
                # IF (THEN) branch SHOULD have status.ready set to 'on'
                ready = child.snapshot.get_attribute_value("status.ready")
                assert ready == "on", f"IF branch should apply effect: ready={ready}"


class TestRecursiveDeMorgan:
    """Comprehensive tests for recursive De Morgan's law implementation."""

    def test_simple_and_demorgan(self, registry_manager):
        """Test: NOT(A AND B) = NOT(A) OR NOT(B) - creates multiple fail branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_simple_and",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "hot",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # AND with 2 unknowns should have: 1 success + 2 fail branches
        assert len(success_branches) == 1, f"Expected 1 success, got {len(success_branches)}"
        assert len(fail_branches) == 2, f"Expected 2 fail branches (De Morgan OR), got {len(fail_branches)}"

        # Each fail branch should be a simple condition (not compound)
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None
            assert bc.compound_type is None, "Simple fail branch should not be compound"

    def test_simple_or_demorgan(self, registry_manager):
        """Test: NOT(A OR B OR C) = NOT(A) AND NOT(B) AND NOT(C) - single fail branch."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_simple_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # OR with 3 unknowns should have: 3 success + 1 fail branch
        assert len(success_branches) == 3, f"Expected 3 success, got {len(success_branches)}"
        assert len(fail_branches) == 1, f"Expected 1 fail branch (De Morgan AND), got {len(fail_branches)}"

        # The fail branch should be a compound AND
        fb = fail_branches[0]
        bc = fb.branch_condition
        assert bc is not None
        assert bc.compound_type == "and", f"Expected compound AND, got {bc.compound_type}"
        assert len(bc.sub_conditions) == 3, f"Expected 3 sub-conditions, got {len(bc.sub_conditions)}"

    def test_nested_and_inside_or_demorgan(self, registry_manager):
        """Test: NOT((A AND B) OR C) = (NOT(A) OR NOT(B)) AND NOT(C).

        The OR in De Morgan creates multiple fail branches:
        - Branch 1: A fails AND C fails (B unknown)
        - Branch 2: B fails AND C fails (A unknown)
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_nested_and_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Should have 2 fail branches (one for each disjunct of the inner OR)
        # NOT((A AND B) OR C) = (NOT A OR NOT B) AND NOT C
        # This means: (A fails or B fails) AND C fails
        # = 2 branches: {A fails, C fails} and {B fails, C fails}
        assert len(fail_branches) == 2, f"Expected 2 fail branches, got {len(fail_branches)}"

        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None

            # Each fail branch should be AND (combining the failing attributes)
            # OR should never appear in branch conditions - OR means split
            assert bc.compound_type == "and" or bc.compound_type is None

            # reel3 should always fail (from the outer AND)
            reel3_val = fb.snapshot.get_attribute_value("reel3.symbol")
            if isinstance(reel3_val, list):
                assert "seven" not in reel3_val

    def test_nested_or_inside_and_demorgan(self, registry_manager):
        """Test: Structure of De Morgan for conditions with OR inside AND.

        For (A AND B) OR C, De Morgan gives (NOT A OR NOT B) AND NOT C.
        The OR creates multiple fail branches, so we get 2 branches:
        - Branch 1: A fails (reel1 ∈ {not seven}), C fails (reel3 ∈ {not seven})
        - Branch 2: B fails (reel2 ∈ {not seven}), C fails (reel3 ∈ {not seven})
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_or_in_and",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Should have 2 fail branches (OR in De Morgan creates multiple branches)
        assert len(fail_branches) == 2, f"Expected 2 fail branches, got {len(fail_branches)}"

        # Both branches should constrain reel3 (from the AND part of De Morgan)
        for fb in fail_branches:
            reel3_val = fb.snapshot.get_attribute_value("reel3.symbol")
            if isinstance(reel3_val, list):
                assert "seven" not in reel3_val, "reel3 should not contain seven"

        # One branch should constrain reel1, the other should constrain reel2
        reel1_constrained = 0
        reel2_constrained = 0
        for fb in fail_branches:
            reel1_val = fb.snapshot.get_attribute_value("reel1.symbol")
            reel2_val = fb.snapshot.get_attribute_value("reel2.symbol")

            if isinstance(reel1_val, list) and "seven" not in reel1_val:
                reel1_constrained += 1
            if isinstance(reel2_val, list) and "seven" not in reel2_val:
                reel2_constrained += 1

        assert reel1_constrained >= 1, "At least one branch should constrain reel1"
        assert reel2_constrained >= 1, "At least one branch should constrain reel2"

    def test_deeply_nested_demorgan(self, registry_manager):
        """Test De Morgan creates correct number of branches for nested conditions.

        For (A AND B) OR C, the OR in De Morgan creates multiple branches:
        - 2 fail branches (one for A fails, one for B fails), each also constraining C
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_deep_nested",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Should have 2 fail branches due to the OR in De Morgan
        assert len(fail_branches) == 2, f"Expected 2 fail branches, got {len(fail_branches)}"

        # Each branch condition should NOT have OR (OR means split into branches)
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None

            # Check that no branch condition has OR at any level
            def has_or(bc):
                if bc.compound_type == "or":
                    return True
                if bc.sub_conditions:
                    return any(has_or(sub) for sub in bc.sub_conditions)
                return False

            assert not has_or(bc), "Branch conditions should never have OR (OR means split)"

        # Verify total nodes: 1 root + 3 success + 2 fail = 6
        assert len(tree.nodes) == 6, f"Expected 6 nodes, got {len(tree.nodes)}"

    def test_demorgan_with_known_values(self, registry_manager):
        """Test De Morgan when some values are already known."""
        runner = TreeSimulationRunner(registry_manager)

        # Set heater.temperature to known value that satisfies the condition
        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_demorgan_known",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "hot",  # Known value that satisfies
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Since heater.temperature is known and satisfies, we only have 2 fail branches
        # (for water_tank.level and bean_hopper.amount)
        assert len(fail_branches) == 2, f"Expected 2 fail branches, got {len(fail_branches)}"

        # None of the fail branches should mention heater.temperature
        for fb in fail_branches:
            bc = fb.branch_condition
            assert bc is not None
            assert "heater" not in bc.attribute, f"Known attribute should not be in fail branch: {bc.attribute}"

    def test_demorgan_branch_values_are_complements(self, registry_manager):
        """Test that fail branch values are correct complements."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_complement_values",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_branches) == 1
        fb = fail_branches[0]

        # Check snapshot values - all reels should NOT contain "seven"
        for reel in ["reel1", "reel2", "reel3"]:
            val = fb.snapshot.get_attribute_value(f"{reel}.symbol")
            if isinstance(val, list):
                assert "seven" not in val, f"{reel} should not contain 'seven': {val}"
            else:
                assert val != "seven", f"{reel} should not be 'seven': {val}"

    def test_success_branch_count_for_nested_or(self, registry_manager):
        """Test that nested OR creates correct number of success branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_nested_success",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]

        # For ((A AND B) OR C), we should have success branches for:
        # - A satisfied (from inner AND)
        # - B satisfied (from inner AND)
        # - C satisfied (from outer OR)
        assert len(success_branches) == 3, f"Expected 3 success branches, got {len(success_branches)}"

    def test_all_branches_have_valid_snapshots(self, registry_manager):
        """Test that all branches (success and fail) have valid snapshots."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_valid_snapshots",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        for nid, node in tree.nodes.items():
            if nid == "state0":
                continue

            assert node.snapshot is not None, f"Node {nid} should have a snapshot"

            # All reel values should be valid (either known or a list of valid values)
            for reel in ["reel1", "reel2", "reel3"]:
                val = node.snapshot.get_attribute_value(f"{reel}.symbol")
                valid_symbols = ["cherry", "lemon", "bar", "bell", "seven"]

                if isinstance(val, list):
                    for v in val:
                        assert v in valid_symbols, f"Invalid value {v} in {reel} for node {nid}"
                elif val != "unknown":
                    assert val in valid_symbols, f"Invalid value {val} in {reel} for node {nid}"

    def test_demorgan_preserves_operator(self, registry_manager):
        """Test that De Morgan preserves correct operators (in/equals)."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_operators",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        assert len(fail_branches) == 1
        fb = fail_branches[0]
        bc = fb.branch_condition

        # Check that operators are correct
        for sub in bc.sub_conditions:
            # Multiple values should use "in", single value should use "equals"
            if isinstance(sub.value, list) and len(sub.value) > 1:
                assert sub.operator == "in", f"Expected 'in' operator for list, got {sub.operator}"
            elif isinstance(sub.value, str):
                assert sub.operator == "equals", f"Expected 'equals' operator for string, got {sub.operator}"


class TestRecursiveDeMorganEdgeCases:
    """Edge case tests for recursive De Morgan implementation."""

    def test_no_or_in_any_branch_condition(self, registry_manager):
        """Verify OR never appears in branch conditions - OR means split."""
        runner = TreeSimulationRunner(registry_manager)

        # Test nested compound
        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_no_or",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        def has_or_recursive(bc):
            if bc is None:
                return False
            if bc.compound_type == "or":
                return True
            if bc.sub_conditions:
                return any(has_or_recursive(sub) for sub in bc.sub_conditions)
            return False

        for nid, node in tree.nodes.items():
            if node.branch_condition:
                assert not has_or_recursive(node.branch_condition), (
                    f"Node {nid} has OR in branch condition - OR should split into branches"
                )

    def test_and_with_three_unknowns_creates_three_fail(self, registry_manager):
        """AND with 3 unknowns should create 3 fail branches (De Morgan OR)."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "brew_espresso", "parameters": {}}],
            simulation_id="test_and_3fail",
            initial_values={
                "water_tank.level": "unknown",
                "bean_hopper.amount": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # 3 unknowns in AND -> 3 fail branches (one per failing attribute)
        assert len(fail_branches) == 3, f"Expected 3 fail branches, got {len(fail_branches)}"

    def test_or_with_three_unknowns_creates_one_compound_fail(self, registry_manager):
        """OR with 3 unknowns should create 1 fail branch with AND of 3 complements."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_or_1fail",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # 3 unknowns in OR -> 1 fail branch (all must fail)
        assert len(fail_branches) == 1, f"Expected 1 fail branch, got {len(fail_branches)}"

        # The branch should have compound AND with 3 sub-conditions
        bc = fail_branches[0].branch_condition
        assert bc.compound_type == "and"
        assert len(bc.sub_conditions) == 3

    def test_known_value_reduces_fail_branches(self, registry_manager):
        """Known values that satisfy should reduce fail branch count."""
        runner = TreeSimulationRunner(registry_manager)

        # With reel3 known as seven (satisfies OR), no fail branches needed
        tree = runner.run(
            "slot_machine",
            [{"name": "check_any_seven", "parameters": {}}],
            simulation_id="test_known_reduces",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "seven",  # Known, satisfies
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # With one satisfying known value, OR always succeeds - no fail branches
        assert len(fail_branches) == 0, f"Expected 0 fail branches, got {len(fail_branches)}"

    def test_nested_demorgan_creates_correct_branch_count(self, registry_manager):
        """Nested (A AND B) OR C should create 3 success + 2 fail."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_branch_count",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        success = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "ok"]
        fail = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # (A AND B) OR C with all unknown:
        # Success: 3 (A satisfies, B satisfies, C satisfies)
        # Fail: 2 (A fails + C fails, B fails + C fails) - De Morgan OR splits
        assert len(success) == 3, f"Expected 3 success, got {len(success)}"
        assert len(fail) == 2, f"Expected 2 fail, got {len(fail)}"

    def test_each_fail_branch_has_unique_constraint(self, registry_manager):
        """Each fail branch should constrain different attributes."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_unique_constraints",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        root = tree.nodes["state0"]
        fail_branches = [tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].action_status == "rejected"]

        # Collect which attributes are constrained (not seven) in each branch
        constrained_attrs = []
        for fb in fail_branches:
            attrs = set()
            for reel in ["reel1", "reel2"]:
                val = fb.snapshot.get_attribute_value(f"{reel}.symbol")
                if isinstance(val, list) and "seven" not in val:
                    attrs.add(reel)
            constrained_attrs.append(frozenset(attrs))

        # Each branch should have a different constraint pattern
        assert len(set(constrained_attrs)) == len(fail_branches), (
            "Each fail branch should have unique constraint pattern"
        )

    def test_postcondition_and_creates_multiple_else_branches(self, registry_manager):
        """AND in postcondition should create multiple ELSE branches."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_postcond_else",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]
        else_branches = [
            tree.nodes[cid]
            for cid in root.children_ids
            if tree.nodes[cid].branch_condition and tree.nodes[cid].branch_condition.branch_type == "else"
        ]

        # AND with 2 unknowns in postcondition -> 2 else branches
        assert len(else_branches) == 2, f"Expected 2 else branches, got {len(else_branches)}"

    def test_deeply_nested_all_configs_valid(self, registry_manager):
        """All branch configurations should have valid world states."""
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "slot_machine",
            [{"name": "nested_compound", "parameters": {}}],
            simulation_id="test_valid_configs",
            initial_values={
                "reel1.symbol": "unknown",
                "reel2.symbol": "unknown",
                "reel3.symbol": "unknown",
            },
        )

        valid_symbols = ["cherry", "lemon", "bar", "bell", "seven"]

        for nid, node in tree.nodes.items():
            for reel in ["reel1", "reel2", "reel3"]:
                val = node.snapshot.get_attribute_value(f"{reel}.symbol")
                if isinstance(val, list):
                    for v in val:
                        assert v in valid_symbols, f"Invalid value {v} in {nid}"
                elif val != "unknown":
                    assert val in valid_symbols, f"Invalid value {val} in {nid}"


class TestNestedPostconditionLimitations:
    """Test documenting known limitations of nested postconditions."""

    def test_nested_if_in_else_branches_at_first_level_only(self, registry_manager):
        """
        Currently, nested conditionals inside else branches
        create branches at the first level only.
        This is a known limitation.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_status", "parameters": {}}],
            simulation_id="test_nested_limit",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        # Current behavior: 3 nodes (initial + 2 branches for first condition)
        # NOT 4 nodes (which would be ideal with recursive branching)
        assert len(tree.nodes) == 3

        # The else branch evaluates nested conditional but doesn't branch
        root = tree.nodes["state0"]
        assert len(root.children_ids) == 2

        # One is IF (water >= medium), one is ELSE
        children = [tree.nodes[cid] for cid in root.children_ids]
        if_branch = [c for c in children if c.branch_condition.branch_type == "if"][0]
        else_branch = [c for c in children if c.branch_condition.branch_type == "else"][0]

        # IF branch: water constrained to >= medium
        water_if = if_branch.snapshot.get_attribute_value("water_tank.level")
        assert isinstance(water_if, list)
        assert "medium" in water_if and "high" in water_if and "full" in water_if

        # ELSE branch: water constrained to < medium
        # But temp is NOT branched on (nested limitation)
        water_else = else_branch.snapshot.get_attribute_value("water_tank.level")
        assert isinstance(water_else, list)
        assert "empty" in water_else and "low" in water_else

        # Temperature remains unknown (not branched)
        temp_else = else_branch.snapshot.get_attribute_value("heater.temperature")
        assert temp_else == "unknown"

    def test_compound_at_top_level_branches_correctly(self, registry_manager):
        """
        Compound conditions at the top level of postcondition
        DO branch correctly with De Morgan.
        """
        runner = TreeSimulationRunner(registry_manager)

        tree = runner.run(
            "coffee_machine",
            [{"name": "check_ready", "parameters": {}}],
            simulation_id="test_top_level_compound",
            initial_values={
                "water_tank.level": "unknown",
                "heater.temperature": "unknown",
            },
        )

        root = tree.nodes["state0"]

        # AND condition at top level creates proper branching:
        # 1 success (IF: both conditions met)
        # 2 else (De Morgan: one fails for water, one fails for temp)
        assert len(root.children_ids) == 3

        if_branches = [
            tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].branch_condition.branch_type == "if"
        ]
        else_branches = [
            tree.nodes[cid] for cid in root.children_ids if tree.nodes[cid].branch_condition.branch_type == "else"
        ]

        assert len(if_branches) == 1
        assert len(else_branches) == 2
