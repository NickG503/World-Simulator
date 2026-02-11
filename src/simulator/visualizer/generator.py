"""
HTML Visualization Generator for Simulation Trees.

This module generates interactive HTML visualizations from simulation history YAML files.
Features:
- Graph-based node visualization with circles
- Click on nodes to expand and see state details
- Prepared for branching trees (multiple children per node)
- Side panel for detailed state view
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from simulator.visualizer.js_template import JS_TEMPLATE
from simulator.visualizer.styles import CSS_STYLES


def load_tree_from_yaml(file_path: str) -> Dict[str, Any]:
    """Load simulation tree from YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def generate_html(tree_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """Generate interactive HTML visualization with graph-based layout."""

    simulation_id = tree_data.get("simulation_id", "Unknown")
    object_type = tree_data.get("object_type", "Unknown")
    created_at = tree_data.get("created_at", "Unknown")
    cli_command = tree_data.get("cli_command", "")

    # Convert to JSON for JavaScript
    tree_json = json.dumps(tree_data, indent=2)

    # Inject tree data into JS template
    js_code = JS_TEMPLATE.replace("__TREE_JSON__", tree_json)

    cli_command_html = f'<div class="cli-command">{cli_command}</div>' if cli_command else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simulation: {simulation_id}</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="container">
        <header>
            <div style="flex-grow: 1;">
                <div style="display: flex; align-items: center; gap: 24px;">
                    <div class="logo">Simulation Tree</div>
                    <div class="meta">
                        <span>ID: {simulation_id}</span>
                        <span>Object: {object_type}</span>
                        <span>Date: {created_at}</span>
                    </div>
                </div>
                {cli_command_html}
            </div>
            <div class="header-controls">
                <div class="layer-legend">
                    <div class="legend-item"><span class="legend-dot action"></span>Action</div>
                    <div class="legend-item"><span class="legend-dot solver"></span>Solver</div>
                    <div class="legend-item"><span class="legend-dot time"></span>Time</div>
                    <div class="legend-item"><span class="legend-dot pruned"></span>Pruned</div>
                </div>
            </div>
        </header>

        <div class="graph-container">
            <svg id="graph"></svg>
            <div class="tooltip" id="tooltip"></div>
        </div>

        <div style="display: flex; flex-direction: column; overflow: hidden;">
            <div class="action-panel" id="action-panel">
                <div class="action-panel-header">
                    <h3 id="action-panel-title">Action Details</h3>
                    <span class="action-panel-close" onclick="hideActionPanel()">&#x2715;</span>
                </div>
                <div id="action-panel-content"></div>
            </div>
            <div class="detail-panel empty" id="detail-panel" style="flex: 1; overflow-y: auto;">
                <div class="empty-icon">&#x25C9;</div>
                <p>Click a node to view details</p>
            </div>
        </div>
    </div>

    <script>{js_code}</script>
</body>
</html>
"""

    if output_path:
        with open(output_path, "w") as f:
            f.write(html)

    return html


def generate_visualization(input_path: str, output_path: Optional[str] = None) -> str:
    """
    Generate HTML visualization from a simulation tree YAML file.

    Args:
        input_path: Path to the simulation tree YAML file
        output_path: Optional output path for the HTML file (auto-generated if not provided)

    Returns:
        Path to the generated HTML file
    """
    # Load tree data
    tree_data = load_tree_from_yaml(input_path)

    # Generate output path if not provided
    if not output_path:
        input_file = Path(input_path)
        output_path = str(input_file.parent / f"{input_file.stem}_visualization.html")

    # Generate HTML
    generate_html(tree_data, output_path)

    return output_path


def open_visualization(html_path: str) -> None:
    """Open the visualization in the default web browser."""
    webbrowser.open(f"file://{Path(html_path).absolute()}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m simulator.visualizer.generator <history.yaml> [output.html]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    result = generate_visualization(input_file, output_file)
    print(f"Generated: {result}")

    # Auto-open
    open_visualization(result)
