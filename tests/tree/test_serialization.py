"""
Tests for tree serialization to YAML and HTML visualization.
"""

from pathlib import Path

import yaml

from simulator.core.tree.models import SimulationTree
from simulator.core.tree.tree_runner import TreeSimulationRunner


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
