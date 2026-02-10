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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simulation: {simulation_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        :root {{
            --bg-dark: #0d1117;
            --bg-card: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-dim: #8b949e;
            --accent-cyan: #58a6ff;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-gold: #d29922;
            --accent-purple: #a371f7;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            min-height: 100vh;
            overflow: hidden;
        }}

        .container {{
            display: grid;
            grid-template-columns: 1fr 400px;
            grid-template-rows: auto 1fr;
            height: 100vh;
        }}

        header {{
            grid-column: 1 / -1;
            padding: 16px 24px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 24px;
        }}

        .logo {{
            font-size: 1.5em;
            font-weight: 600;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-green));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .meta {{
            color: var(--text-dim);
            font-size: 0.9em;
            display: flex;
            gap: 20px;
        }}

        .meta span {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .cli-command {{
            margin-top: 8px;
            padding: 8px 12px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border);
            border-radius: 6px;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 0.85em;
            color: var(--accent-cyan);
            overflow-x: auto;
            white-space: nowrap;
        }}

        .cli-command::before {{
            content: '$ ';
            color: var(--accent-green);
        }}

        .header-controls {{
            display: flex;
            gap: 12px;
            margin-left: auto;
        }}

        .toggle-btn {{
            padding: 6px 12px;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-dim);
            cursor: pointer;
            font-size: 0.85em;
            transition: all 0.2s ease;
        }}

        .toggle-btn:hover {{
            border-color: var(--accent-cyan);
            color: var(--text);
        }}

        .toggle-btn.active {{
            border-color: var(--accent-purple);
            color: var(--accent-purple);
            background: rgba(163, 113, 247, 0.1);
        }}

        /* Layer legend */
        .layer-legend {{
            display: flex;
            gap: 16px;
            padding: 8px 16px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            font-size: 0.8em;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            border: 2px solid;
        }}

        .legend-dot.action {{ border-color: var(--accent-green); }}
        .legend-dot.solver {{ border-color: var(--accent-purple); }}
        .legend-dot.time {{ border-color: var(--accent-cyan); }}
        .legend-dot.pruned {{ border-color: #484f58; opacity: 0.5; }}

        .graph-container {{
            position: relative;
            overflow: auto;
            background:
                radial-gradient(circle at 50% 50%, rgba(88, 166, 255, 0.03) 0%, transparent 50%),
                var(--bg-dark);
        }}

        #graph {{
            min-width: 100%;
            min-height: 100%;
        }}

        .detail-panel {{
            background: var(--bg-card);
            border-left: 1px solid var(--border);
            overflow-y: auto;
            padding: 20px;
        }}

        .detail-panel.empty {{
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            color: var(--text-dim);
        }}

        .empty-icon {{
            font-size: 4em;
            margin-bottom: 16px;
            opacity: 0.3;
        }}

        .detail-header {{
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}

        .detail-header h2 {{
            font-size: 1.2em;
            color: var(--accent-cyan);
            margin-bottom: 8px;
        }}

        .detail-header .action {{
            font-size: 1.1em;
            color: var(--text);
        }}

        .detail-header .action.success {{
            color: var(--accent-green);
        }}

        .detail-header .action.failed {{
            color: var(--accent-red);
        }}

        .detail-header .branch {{
            color: var(--text-dim);
            font-size: 0.9em;
            margin-top: 6px;
            line-height: 1.5;
        }}

        .detail-header .branch .compound-connector {{
            color: var(--accent-purple);
            font-weight: 600;
            padding: 0 4px;
        }}

        .detail-header .branch .attr-name {{
            color: var(--accent-blue);
        }}

        .detail-header .branch .operator {{
            color: var(--accent-yellow);
            padding: 0 2px;
        }}

        .detail-header .branch .value-set {{
            color: var(--accent-cyan);
        }}

        .section {{
            margin-bottom: 24px;
        }}

        .section-title {{
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-dim);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            user-select: none;
        }}

        .section-title:hover {{
            color: var(--text);
        }}

        .section-title::before {{
            content: '';
            width: 3px;
            height: 14px;
            background: var(--accent-cyan);
            border-radius: 2px;
        }}

        .section-title::after {{
            content: '▼';
            margin-left: auto;
            font-size: 0.7em;
            transition: transform 0.2s ease;
        }}

        .section.collapsed .section-title::after {{
            transform: rotate(-90deg);
        }}

        .section.collapsed .section-content {{
            display: none;
        }}

        .section-content {{
            transition: max-height 0.2s ease;
        }}

        .attr-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .attr-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 12px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 6px;
            border: 1px solid transparent;
        }}

        .attr-item.changed {{
            border-color: var(--accent-gold);
            background: rgba(210, 153, 34, 0.1);
        }}

        .attr-item.relevant {{
            border-color: var(--accent-green);
            background: rgba(63, 185, 80, 0.1);
        }}

        .attr-name {{
            color: var(--text-dim);
            font-size: 0.9em;
        }}

        .attr-value {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .value {{
            font-weight: 500;
            color: var(--text);
            padding: 2px 8px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 4px;
        }}

        .trend {{
            font-size: 0.8em;
            padding: 2px 6px;
            border-radius: 3px;
        }}

        .trend.up {{
            color: var(--accent-green);
            background: rgba(63, 185, 80, 0.2);
        }}

        .trend.down {{
            color: var(--accent-red);
            background: rgba(248, 81, 73, 0.2);
        }}

        .value.value-set {{
            background: rgba(163, 113, 247, 0.2);
            border: 1px solid var(--accent-purple);
            color: var(--accent-purple);
        }}

        .branch-value-set {{
            color: var(--accent-purple);
        }}

        .change-item {{
            display: grid;
            grid-template-columns: 1fr auto auto auto;
            gap: 8px;
            align-items: center;
            padding: 8px 12px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 6px;
            margin-bottom: 6px;
        }}

        .change-before {{
            color: var(--text-dim);
            text-decoration: line-through;
        }}

        .change-arrow {{
            color: var(--accent-gold);
        }}

        .change-after {{
            color: var(--accent-green);
            font-weight: 500;
        }}

        .expand-btn {{
            color: var(--accent-cyan);
            cursor: pointer;
            font-size: 0.85em;
            margin-top: 8px;
        }}

        .expand-btn:hover {{
            text-decoration: underline;
        }}

        .hidden {{
            display: none !important;
        }}

        /* SVG Styles */
        .node {{
            cursor: pointer;
        }}

        .node-circle {{
            stroke-width: 3;
            transition: stroke-width 0.15s ease, filter 0.15s ease;
        }}

        .node:hover .node-circle {{
            stroke-width: 5;
            filter: drop-shadow(0 0 6px currentColor);
        }}

        .node.root .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-gold);
        }}

        .node.success .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-green);
        }}

        .node.failed .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-red);
        }}

        .node.solver .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-purple);
        }}

        .node.time .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-cyan);
        }}

        .node.constraint .node-circle {{
            fill: var(--bg-card);
            stroke: var(--accent-cyan);
        }}

        .node.pruned .node-circle {{
            fill: var(--bg-card);
            stroke: #484f58;
            opacity: 0.35;
        }}

        .node.pruned .node-label {{
            opacity: 0.35;
        }}

        .node.selected .node-circle {{
            stroke-width: 4;
            filter: drop-shadow(0 0 8px currentColor);
        }}

        .node-label {{
            font-family: inherit;
            font-size: 11px;
            fill: var(--text);
            text-anchor: middle;
            pointer-events: none;
        }}


        .edge {{
            stroke: var(--border);
            stroke-width: 2;
            fill: none;
        }}

        .edge.active {{
            stroke: var(--accent-cyan);
            stroke-width: 3;
        }}

        .edge.pruned-edge {{
            stroke: #484f58;
            opacity: 0.25;
            stroke-dasharray: 4 3;
        }}


        /* Action label on the left side per level */
        .level-action {{
            font-size: 13px;
            fill: var(--text);
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }}

        /* Tooltip */
        .tooltip {{
            position: absolute;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
            z-index: 100;
            max-width: 300px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}

        .tooltip.visible {{
            opacity: 1;
        }}

        .tooltip-title {{
            font-weight: 600;
            color: var(--accent-cyan);
            margin-bottom: 4px;
        }}

        .tooltip-action {{
            color: var(--text);
        }}

        .tooltip-hint {{
            color: var(--text-dim);
            font-size: 0.85em;
            margin-top: 8px;
        }}

        /* Action Detail Panel */
        .action-panel {{
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease, padding 0.3s ease;
            padding: 0 20px;
        }}

        .action-panel.visible {{
            max-height: 400px;
            padding: 16px 20px;
            overflow-y: auto;
        }}

        .action-panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}

        .action-panel-header h3 {{
            font-size: 1.1em;
            color: var(--accent-purple);
            margin: 0;
        }}

        .action-panel-close {{
            cursor: pointer;
            color: var(--text-dim);
            font-size: 1.2em;
            padding: 4px 8px;
            border-radius: 4px;
            transition: background 0.2s;
        }}

        .action-panel-close:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: var(--text);
        }}

        .condition-section {{
            margin-bottom: 16px;
        }}

        .condition-section-title {{
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-dim);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .condition-section-title::before {{
            content: '';
            width: 3px;
            height: 12px;
            border-radius: 2px;
        }}

        .condition-section-title.precondition::before {{
            background: var(--accent-cyan);
        }}

        .condition-section-title.effects::before {{
            background: var(--accent-green);
        }}

        .condition-tree {{
            font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
            font-size: 0.85em;
            line-height: 1.6;
        }}

        .condition-block {{
            padding: 8px 12px;
            border-left: 3px solid var(--border);
            background: rgba(255, 255, 255, 0.02);
            margin: 4px 0;
            border-radius: 0 4px 4px 0;
        }}

        .condition-block.if {{
            border-left-color: var(--accent-green);
        }}

        .condition-block.elif {{
            border-left-color: var(--accent-gold);
        }}

        .condition-block.else {{
            border-left-color: var(--accent-red);
        }}

        .condition-block.or {{
            border-left-color: var(--accent-purple);
        }}

        .condition-block.and {{
            border-left-color: var(--accent-cyan);
        }}

        .condition-keyword {{
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            margin-right: 8px;
        }}

        .condition-keyword.if {{ color: var(--accent-green); }}
        .condition-keyword.elif {{ color: var(--accent-gold); }}
        .condition-keyword.else {{ color: var(--accent-red); }}
        .condition-keyword.or {{ color: var(--accent-purple); }}
        .condition-keyword.and {{ color: var(--accent-cyan); }}

        .condition-expr {{
            color: var(--text);
        }}

        .condition-expr .attr {{
            color: var(--accent-cyan);
        }}

        .condition-expr .op {{
            color: var(--accent-gold);
            padding: 0 4px;
        }}

        .condition-expr .val {{
            color: var(--accent-green);
        }}

        .effect-arrow {{
            color: var(--accent-purple);
            margin: 0 4px;
        }}

        .effect-target {{
            color: var(--accent-cyan);
        }}

        .effect-value {{
            color: var(--accent-green);
        }}

        .nested-conditions {{
            margin-left: 16px;
            padding-left: 8px;
            border-left: 1px dashed var(--border);
        }}

        /* Make action labels clickable */
        .level-action {{
            cursor: pointer;
            transition: fill 0.2s;
        }}

        .level-action:hover {{
            fill: var(--accent-purple);
        }}

        .level-action.selected {{
            fill: var(--accent-purple);
            font-weight: 700;
        }}
    </style>
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
                {f'<div class="cli-command">{cli_command}</div>' if cli_command else ""}
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
                    <span class="action-panel-close" onclick="hideActionPanel()">✕</span>
                </div>
                <div id="action-panel-content"></div>
            </div>
            <div class="detail-panel empty" id="detail-panel" style="flex: 1; overflow-y: auto;">
                <div class="empty-icon">◉</div>
                <p>Click a node to view details</p>
            </div>
        </div>
    </div>

    <script>
        const treeData = {tree_json};

        let selectedNodeId = null;
        let selectedActionName = null;
        let selectedLabelType = null;  // 'solver' or 'time'
        const sectionStates = {{}};  // Track collapsed state per node
        const otherAttrsStates = {{}};  // Track "other attributes" expanded state per node
        const collapsedActionIndices = new Set();  // Track which action INDICES (instances) are collapsed
        const NODE_RADIUS = 28;
        const LEVEL_HEIGHT = 100;        // Vertical distance between levels
        const NODE_SPACING = 70;         // Minimum space between node centers

        // Build a map from action node IDs to their instance index in the action sequence
        // This allows distinguishing between multiple occurrences of the same action name
        const actionNodeToIndex = {{}};
        const actionIndexToNodes = {{}};

        function buildActionInstanceMaps() {{
            const nodes = treeData.nodes || {{}};
            const actionSequence = treeData.actions || [];

            // For each action in sequence, find which action nodes belong to it
            // Action nodes belong to an instance if they match the name AND come in the right order
            const actionCounts = {{}};  // Track how many times each action name has been seen

            // First, collect all action nodes and their depths
            const actionNodes = [];
            for (const [nodeId, node] of Object.entries(nodes)) {{
                if (node.node_type === 'action' && node.action_name) {{
                    // Calculate depth by walking up to root
                    let depth = 0;
                    let currentId = nodeId;
                    const visited = new Set();
                    while (currentId && !visited.has(currentId)) {{
                        visited.add(currentId);
                        const n = nodes[currentId];
                        if (!n) break;
                        if (n.node_type === 'root') break;
                        const parents = n.parent_ids || [];
                        if (parents.length > 0) {{
                            currentId = parents[0];
                            depth++;
                        }} else {{
                            break;
                        }}
                    }}
                    actionNodes.push({{ nodeId, node, depth, actionName: node.action_name }});
                }}
            }}

            // Sort by depth to process in order
            actionNodes.sort((a, b) => a.depth - b.depth);

            // Now assign each action node to an instance index based on depth and sequence
            // Group by depth first
            const byDepth = {{}};
            for (const an of actionNodes) {{
                if (!byDepth[an.depth]) byDepth[an.depth] = [];
                byDepth[an.depth].push(an);
            }}

            // For each depth level, assign instance indices
            // Assumption: at each depth, all action nodes with the same name belong to the same instance
            const depths = Object.keys(byDepth).map(Number).sort((a, b) => a - b);
            let currentSequenceIdx = 0;

            for (const depth of depths) {{
                const nodesAtDepth = byDepth[depth];
                // Get unique action names at this depth
                const namesAtDepth = [...new Set(nodesAtDepth.map(n => n.actionName))];

                for (const name of namesAtDepth) {{
                    // Find which instance index this corresponds to
                    // It should be the next occurrence of this name in the sequence
                    while (currentSequenceIdx < actionSequence.length &&
                           actionSequence[currentSequenceIdx] !== name) {{
                        currentSequenceIdx++;
                    }}

                    if (currentSequenceIdx < actionSequence.length) {{
                        // Assign all nodes with this name at this depth to this instance
                        for (const an of nodesAtDepth) {{
                            if (an.actionName === name) {{
                                actionNodeToIndex[an.nodeId] = currentSequenceIdx;
                                if (!actionIndexToNodes[currentSequenceIdx]) {{
                                    actionIndexToNodes[currentSequenceIdx] = [];
                                }}
                                actionIndexToNodes[currentSequenceIdx].push(an.nodeId);
                            }}
                        }}
                        currentSequenceIdx++;
                    }}
                }}
            }}
        }}
        buildActionInstanceMaps();

        // Toggle collapse state for an action by INDEX
        function toggleActionCollapse(actionIndex) {{
            if (collapsedActionIndices.has(actionIndex)) {{
                collapsedActionIndices.delete(actionIndex);
            }} else {{
                collapsedActionIndices.add(actionIndex);
            }}
            renderGraph();
        }}

        // Check if a node is an intermediate layer (solver/time)
        function isIntermediateNode(node) {{
            const nodeType = node.node_type || 'action';
            return nodeType === 'solver' || nodeType === 'time' || nodeType === 'constraint';
        }}

        // Find the action instance INDEX that this node belongs to
        function findParentActionIndex(nodeId) {{
            const nodes = treeData.nodes || {{}};
            const visited = new Set();

            function search(currentId) {{
                if (visited.has(currentId)) return null;
                visited.add(currentId);

                const node = nodes[currentId];
                if (!node) return null;

                // If this is an action node, return its instance index
                if (node.node_type === 'action' && actionNodeToIndex[currentId] !== undefined) {{
                    return actionNodeToIndex[currentId];
                }}

                // If root, stop
                if (node.node_type === 'root') return null;

                // Look at parents
                const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
                for (const parentId of parentIds) {{
                    const result = search(parentId);
                    if (result !== null) return result;
                }}
                return null;
            }}

            return search(nodeId);
        }}

        // Find the action name that this intermediate node belongs to (for display purposes)
        function findParentActionName(nodeId) {{
            const actionIndex = findParentActionIndex(nodeId);
            if (actionIndex !== null) {{
                const actionSequence = treeData.actions || [];
                return actionSequence[actionIndex] || null;
            }}
            return null;
        }}

        // Find all leaf nodes (nodes with no children) in a subtree
        function findLeafNodes(nodeId) {{
            const nodes = treeData.nodes || {{}};
            const node = nodes[nodeId];
            if (!node) return [];

            const children = node.children_ids || [];
            if (children.length === 0) {{
                return [nodeId];
            }}

            const leaves = [];
            for (const childId of children) {{
                leaves.push(...findLeafNodes(childId));
            }}
            return leaves;
        }}

        // Find "action boundary" nodes - the last nodes before the next action starts
        // These are nodes that either have no children OR whose children are all action nodes
        function findActionBoundaryNodes(actionNodeId) {{
            // When an action is collapsed, find the next visible nodes to show
            // Skip intermediate (solver/time/constraint) nodes and return next action nodes or leaves
            const nodes = treeData.nodes || {{}};
            const actionNode = nodes[actionNodeId];
            if (!actionNode) return [];

            const boundaryNodes = [];
            const visited = new Set();

            function traverse(nodeId) {{
                if (visited.has(nodeId)) return;
                visited.add(nodeId);

                const node = nodes[nodeId];
                if (!node) return;

                // If this is an ACTION node (not the starting one), it's a boundary
                if (node.node_type === 'action') {{
                    boundaryNodes.push(nodeId);
                    return;
                }}

                const children = node.children_ids || [];

                // If no children, this is a leaf intermediate node - include it
                if (children.length === 0) {{
                    boundaryNodes.push(nodeId);
                    return;
                }}

                // Continue traversing through intermediate nodes
                for (const childId of children) {{
                    traverse(childId);
                }}
            }}

            // Start from the action node's children (skip the action node itself)
            const children = actionNode.children_ids || [];
            for (const childId of children) {{
                traverse(childId);
            }}

            return boundaryNodes;
        }}

        // Check if an action has intermediate children (solver/time/constraint nodes)
        function hasIntermediateChildren(actionNodeId) {{
            const nodes = treeData.nodes || {{}};
            const actionNode = nodes[actionNodeId];
            if (!actionNode) return false;

            const children = actionNode.children_ids || [];
            for (const childId of children) {{
                const child = nodes[childId];
                if (child && isIntermediateNode(child)) {{
                    return true;
                }}
            }}
            return false;
        }}

        // Check if a node should be visible
        function isNodeVisible(node, nodeId) {{
            // Root is always visible
            if (node.node_type === 'root') {{
                return true;
            }}

            // Action nodes visibility rules
            if (node.node_type === 'action') {{
                const status = node.action_status || 'ok';

                // FAILED action nodes are ALWAYS visible - they are terminal (red nodes)
                if (status !== 'ok') {{
                    return true;
                }}

                // Successful action nodes: hide when collapsed, show when expanded
                const actionIndex = actionNodeToIndex[nodeId];
                if (actionIndex !== null && actionIndex !== undefined && collapsedActionIndices.has(actionIndex)) {{
                    return false;
                }}
                return true;
            }}

            // For intermediate nodes (solver/time/constraint)
            if (isIntermediateNode(node)) {{
                const children = node.children_ids || [];

                // LEAF intermediate nodes (no children) are ALWAYS visible
                // These are the final outputs of an action chain
                if (children.length === 0) {{
                    return true;
                }}

                // Check if all children are action nodes (this node is the last before next action)
                const nodes = treeData.nodes || {{}};
                const allChildrenAreActions = children.every(childId => {{
                    const child = nodes[childId];
                    return child && child.node_type === 'action';
                }});

                // If all children are actions, this is a "boundary" solver - ALWAYS show it
                // When collapsed: this is the visible result (purple)
                // When expanded: still visible as part of the chain
                if (allChildrenAreActions) {{
                    return true;
                }}

                // Otherwise, hide if parent action is collapsed
                const parentActionIndex = findParentActionIndex(nodeId);
                if (parentActionIndex !== null && collapsedActionIndices.has(parentActionIndex)) {{
                    return false;
                }}
            }}

            return true;
        }}

        // Get visible children of a node (skips hidden nodes)
        function getVisibleChildren(nodeId) {{
            const nodes = treeData.nodes || {{}};
            const node = nodes[nodeId];
            if (!node) return [];

            const directChildren = node.children_ids || [];

            // Return visible children, recursively skipping hidden nodes
            const result = [];
            for (const childId of directChildren) {{
                const childNode = nodes[childId];
                if (!childNode) continue;

                if (isNodeVisible(childNode, childId)) {{
                    result.push(childId);
                }} else {{
                    // Child is hidden, get its visible children recursively
                    result.push(...getVisibleChildren(childId));
                }}
            }}
            return result;
        }}

        // Get all visible node IDs
        function getVisibleNodeIds() {{
            const nodes = treeData.nodes || {{}};
            const visibleIds = [];
            for (const [id, node] of Object.entries(nodes)) {{
                if (isNodeVisible(node, id)) {{
                    visibleIds.push(id);
                }}
            }}
            return visibleIds;
        }}

        // Calculate tree layout using a simple level-based algorithm
        // This is more robust for DAG structures and prevents overlapping
        function calculateLayout() {{
            const nodes = treeData.nodes || {{}};
            const rootId = treeData.root_id;
            const layout = {{}};

            // Build adjacency list using visible children
            const children = {{}};
            for (const [id, node] of Object.entries(nodes)) {{
                if (isNodeVisible(node, id)) {{
                    children[id] = getVisibleChildren(id);
                }}
            }}

            // Calculate depth (level) for each visible node using BFS
            // This handles DAGs correctly by taking the minimum depth
            const depths = {{}};
            const visited = new Set();
            const queue = [[rootId, 0]];

            while (queue.length > 0) {{
                const [nodeId, depth] = queue.shift();
                const node = nodes[nodeId];
                if (!node || !isNodeVisible(node, nodeId)) continue;
                if (visited.has(nodeId)) continue;

                visited.add(nodeId);
                depths[nodeId] = depth;

                for (const childId of children[nodeId] || []) {{
                    if (!visited.has(childId)) {{
                        queue.push([childId, depth + 1]);
                    }}
                }}
            }}

            // Group nodes by their level
            const levels = {{}};
            let maxLevel = 0;
            for (const [nodeId, depth] of Object.entries(depths)) {{
                if (!levels[depth]) levels[depth] = [];
                levels[depth].push(nodeId);
                maxLevel = Math.max(maxLevel, depth);
            }}

            // Position nodes within each level
            // Use a simple even distribution with minimum spacing
            let maxWidth = 0;
            const MIN_NODE_SPACING = NODE_SPACING + 10;  // Minimum space between node centers

            for (let level = 0; level <= maxLevel; level++) {{
                const nodesAtLevel = levels[level] || [];
                const count = nodesAtLevel.length;

                if (count === 0) continue;

                // Calculate total width needed for this level
                const levelWidth = (count - 1) * MIN_NODE_SPACING;
                const startX = -levelWidth / 2;

                // Sort nodes to minimize edge crossings
                // Try to place children near their parents
                if (level > 0) {{
                    nodesAtLevel.sort((a, b) => {{
                        const nodeA = nodes[a];
                        const nodeB = nodes[b];
                        const parentA = (nodeA.parent_ids || [])[0];
                        const parentB = (nodeB.parent_ids || [])[0];
                        const posA = parentA && layout[parentA] ? layout[parentA].x : 0;
                        const posB = parentB && layout[parentB] ? layout[parentB].x : 0;
                        return posA - posB;
                    }});
                }}

                // Assign x positions
                nodesAtLevel.forEach((nodeId, idx) => {{
                    const x = startX + idx * MIN_NODE_SPACING;
                    layout[nodeId] = {{
                        x: x,
                        y: level * LEVEL_HEIGHT + NODE_RADIUS + 40,
                        level: level
                    }};
                    maxWidth = Math.max(maxWidth, Math.abs(x));
                }});
            }}

            // Second pass: try to center parents over their children
            for (let level = maxLevel - 1; level >= 0; level--) {{
                const nodesAtLevel = levels[level] || [];

                for (const nodeId of nodesAtLevel) {{
                    const childIds = children[nodeId] || [];
                    if (childIds.length === 0) continue;

                    // Calculate average position of children
                    let sumX = 0;
                    let count = 0;
                    for (const childId of childIds) {{
                        if (layout[childId]) {{
                            sumX += layout[childId].x;
                            count++;
                        }}
                    }}

                    if (count > 0) {{
                        const targetX = sumX / count;
                        // Only move if it doesn't cause overlap with siblings
                        const siblings = levels[level];
                        const myIdx = siblings.indexOf(nodeId);
                        const leftNeighbor = myIdx > 0 ? layout[siblings[myIdx - 1]] : null;
                        const rightNeighbor = myIdx < siblings.length - 1 ? layout[siblings[myIdx + 1]] : null;

                        let newX = targetX;
                        if (leftNeighbor && newX < leftNeighbor.x + MIN_NODE_SPACING) {{
                            newX = leftNeighbor.x + MIN_NODE_SPACING;
                        }}
                        if (rightNeighbor && newX > rightNeighbor.x - MIN_NODE_SPACING) {{
                            newX = rightNeighbor.x - MIN_NODE_SPACING;
                        }}

                        layout[nodeId].x = newX;
                        maxWidth = Math.max(maxWidth, Math.abs(newX));
                    }}
                }}
            }}

            return {{ layout, maxWidth, maxLevel }};
        }}

        function renderGraph() {{
            const svg = document.getElementById('graph');
            const {{ layout, maxWidth, maxLevel }} = calculateLayout();

            // Set SVG size
            const width = Math.max(800, maxWidth * 2 + 200);
            const height = (maxLevel + 1) * LEVEL_HEIGHT + 100;
            svg.setAttribute('viewBox', `${{-width/2}} 0 ${{width}} ${{height}}`);
            svg.style.width = width + 'px';
            svg.style.height = height + 'px';

            let html = '';

            // ============================================
            // SIMPLIFIED LABEL SYSTEM
            // ============================================
            //
            // The key insight: labels should be placed based on the ACTION SEQUENCE,
            // not based on level numbers. The action sequence is the same regardless
            // of which actions are collapsed/expanded.
            //
            // For each action in sequence:
            //   - Find the Y position where that action's nodes appear (or boundary if collapsed)
            //   - Place label between the previous action's area and this action's area
            //
            // For solver/time labels:
            //   - Only show them at levels where there's no action label

            const nodes = treeData.nodes || {{}};
            const leftX = -width / 2 + 60;
            const actionSequence = treeData.actions || [];

            // Draw edges first (so they're behind nodes)
            for (const [nodeId, node] of Object.entries(nodes)) {{
                if (!isNodeVisible(node, nodeId)) continue;

                const pos = layout[nodeId];
                if (!pos) continue;

                const visibleKids = getVisibleChildren(nodeId);

                for (const childId of visibleKids) {{
                    const childNode = nodes[childId];
                    if (!childNode) continue;

                    const childPos = layout[childId];
                    if (!childPos) continue;

                    const midY = (pos.y + childPos.y) / 2;
                    const pathD = `M${{pos.x}},${{pos.y + NODE_RADIUS}} ` +
                                  `Q${{pos.x}},${{midY}} ${{childPos.x}},${{childPos.y - NODE_RADIUS}}`;

                    const edgeClass = (childNode.pruned || node.pruned) ? 'edge pruned-edge' : 'edge';
                    html += `<path class="${{edgeClass}}" d="${{pathD}}" />`;
                }}
            }}

            // ============================================
            // BUILD LABEL LIST FROM ACTION SEQUENCE (BY INSTANCE INDEX)
            // ============================================

            // For each action INSTANCE, find the minimum Y position of nodes belonging to it
            // (either action node itself if expanded, or boundary nodes if collapsed)
            const actionInstanceYPositions = {{}};  // Map from instance index to {{ minY, maxY }}

            for (let instanceIdx = 0; instanceIdx < actionSequence.length; instanceIdx++) {{
                let minY = Infinity;
                let maxY = -Infinity;

                // Find all visible nodes that belong to this action instance
                for (const [nodeId, pos] of Object.entries(layout)) {{
                    const node = nodes[nodeId];
                    if (!node) continue;

                    // Check if this node belongs to this action instance
                    const parentActionIdx = findParentActionIndex(nodeId);
                    if (parentActionIdx === instanceIdx) {{
                        minY = Math.min(minY, pos.y);
                        maxY = Math.max(maxY, pos.y);
                    }}

                    // Also check if this IS the action node for this instance
                    if (node.node_type === 'action' && actionNodeToIndex[nodeId] === instanceIdx) {{
                        minY = Math.min(minY, pos.y);
                        maxY = Math.max(maxY, pos.y);
                    }}
                }}

                if (minY !== Infinity) {{
                    actionInstanceYPositions[instanceIdx] = {{ minY, maxY }};
                }}
            }}

            // Build labels array with proper Y ordering based on action sequence
            const labelsToRender = [];
            let prevMaxY = layout[treeData.root_id]?.y || 0;  // Start after root

            for (let instanceIdx = 0; instanceIdx < actionSequence.length; instanceIdx++) {{
                const actionName = actionSequence[instanceIdx];
                const positions = actionInstanceYPositions[instanceIdx];

                if (!positions) continue;

                // Label Y = midpoint between previous action's end and this action's start
                const labelY = (prevMaxY + positions.minY) / 2;

                labelsToRender.push({{
                    type: 'action',
                    name: actionName,
                    instanceIndex: instanceIdx,  // Track instance for click handling
                    y: labelY,
                    isCollapsed: collapsedActionIndices.has(instanceIdx),
                    hasFailure: false  // Will check below
                }});

                // Check for failures in this action instance's nodes
                const instanceNodes = actionIndexToNodes[instanceIdx] || [];
                for (const nodeId of instanceNodes) {{
                    const node = nodes[nodeId];
                    if (node && node.action_status !== 'ok') {{
                        labelsToRender[labelsToRender.length - 1].hasFailure = true;
                        break;
                    }}
                }}

                prevMaxY = positions.maxY;
            }}

            // Now add Solver/Time labels for intermediate nodes
            // ONLY show these labels when the parent action is EXPANDED
            const actionLabelYs = new Set(labelsToRender.map(l => Math.round(l.y)));
            const solverTimeLabels = [];

            for (const [nodeId, node] of Object.entries(nodes)) {{
                if (!isNodeVisible(node, nodeId)) continue;
                const pos = layout[nodeId];
                if (!pos) continue;

                const nodeType = node.node_type || 'action';
                if (nodeType !== 'solver' && nodeType !== 'time' && nodeType !== 'constraint') continue;

                // CRITICAL: Only show solver/time labels when parent action is EXPANDED
                // If the parent action is collapsed, the intermediate nodes are hidden
                // and showing a label would be confusing ("out of nowhere")
                const parentActionIndex = findParentActionIndex(nodeId);
                if (parentActionIndex !== null && collapsedActionIndices.has(parentActionIndex)) {{
                    continue;  // Skip label for collapsed action's intermediate nodes
                }}

                // Find the previous visible node to calculate label Y
                const parentIds = node.parent_ids || [];
                let parentY = pos.y - LEVEL_HEIGHT;
                for (const pid of parentIds) {{
                    if (layout[pid]) {{
                        parentY = layout[pid].y;
                        break;
                    }}
                }}

                const labelY = (parentY + pos.y) / 2;
                const roundedY = Math.round(labelY);

                // Skip if too close to an action label
                let tooClose = false;
                for (const aY of actionLabelYs) {{
                    if (Math.abs(roundedY - aY) < 30) {{
                        tooClose = true;
                        break;
                    }}
                }}
                if (tooClose) continue;

                // Check if we already have a label at this Y position
                const existingLabel = solverTimeLabels.find(l => Math.abs(Math.round(l.y) - roundedY) < 30);
                if (!existingLabel) {{
                    solverTimeLabels.push({{
                        type: nodeType === 'solver' ? 'solver' : 'time',
                        y: labelY
                    }});
                }}
            }}

            // Merge solver/time labels into main list
            labelsToRender.push(...solverTimeLabels);

            // Sort by Y position
            labelsToRender.sort((a, b) => a.y - b.y);

            // Final collision avoidance pass
            const MIN_LABEL_SPACING = 28;
            const usedYPositions = [];

            for (const label of labelsToRender) {{
                let y = label.y;

                for (const usedY of usedYPositions) {{
                    if (Math.abs(y - usedY) < MIN_LABEL_SPACING) {{
                        y = usedY + MIN_LABEL_SPACING;
                    }}
                }}

                label.y = y;
                usedYPositions.push(y);
            }}

            // Render all labels
            for (const label of labelsToRender) {{
                if (label.type === 'action') {{
                    const isSelected = selectedActionName === label.name;
                    let labelClass = 'level-action';
                    if (label.hasFailure) labelClass += ' has-failure';
                    if (isSelected) labelClass += ' selected';

                    const toggleIcon = label.isCollapsed ? '+' : '−';
                    const toggleColor = label.isCollapsed ? 'var(--accent-gold)' : 'var(--text-dim)';
                    const toggleX = leftX - 25;

                    html += `
                        <g transform="translate(${{toggleX}}, ${{label.y}})"
                           onclick="event.stopPropagation(); toggleActionCollapse(${{label.instanceIndex}})"
                           style="cursor: pointer;">
                            <circle r="10" fill="var(--bg-card)" stroke="${{toggleColor}}" stroke-width="1.5" />
                            <text y="4" fill="${{toggleColor}}" font-size="14" font-weight="bold"
                                  text-anchor="middle">${{toggleIcon}}</text>
                        </g>
                    `;

                    html += `<text class="${{labelClass}}" x="${{leftX}}" y="${{label.y}}" ` +
                        `text-anchor="start" onclick="toggleActionPanel('${{label.name}}')" ` +
                        `style="cursor: pointer;">${{label.name}}</text>`;

                }} else if (label.type === 'solver') {{
                    const labelClass = selectedLabelType === 'solver' ? 'level-action selected' : 'level-action';
                    html += `<text class="${{labelClass}}" x="${{leftX}}" y="${{label.y}}" ` +
                        `text-anchor="start" onclick="showLabelPanel('solver')" ` +
                        `style="cursor: pointer; fill: var(--accent-purple);">Solver</text>`;

                }} else if (label.type === 'time') {{
                    const labelClass = selectedLabelType === 'time' ? 'level-action selected' : 'level-action';
                    html += `<text class="${{labelClass}}" x="${{leftX}}" y="${{label.y}}" ` +
                        `text-anchor="start" onclick="showLabelPanel('time')" ` +
                        `style="cursor: pointer; fill: var(--accent-cyan);">Time</text>`;
                }}
            }}

            // Draw nodes (only visible ones)
            for (const [nodeId, node] of Object.entries(nodes)) {{
                // Skip hidden nodes
                if (!isNodeVisible(node, nodeId)) continue;

                const pos = layout[nodeId];
                if (!pos) continue;

                // DAG support: check parent_ids array
                const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
                const isRoot = parentIds.length === 0;
                const isSelected = nodeId === selectedNodeId;
                const status = node.action_status || 'ok';
                const nodeType = node.node_type || 'action';

                // Determine status class based on node_type
                const isPruned = node.pruned === true;
                let statusClass;
                if (isPruned) {{
                    statusClass = 'pruned';
                }} else if (isRoot) {{
                    statusClass = 'root';
                }} else if (nodeType === 'solver') {{
                    statusClass = 'solver';
                }} else if (nodeType === 'time') {{
                    statusClass = 'time';
                }} else if (nodeType === 'constraint') {{
                    statusClass = 'constraint';
                }} else if (status !== 'ok') {{
                    statusClass = 'failed';
                }} else {{
                    statusClass = 'success';
                }}

                const classes = `node ${{statusClass}} ${{isSelected ? 'selected' : ''}}`;
                html += `
                    <g class="${{classes.trim()}}"
                       data-node-id="${{nodeId}}"
                       transform="translate(${{pos.x}}, ${{pos.y}})"
                       onclick="selectNode('${{nodeId}}')"
                       onmouseenter="showTooltip(event, '${{nodeId}}')"
                       onmouseleave="hideTooltip()">
                        <circle class="node-circle" r="${{NODE_RADIUS}}" cx="0" cy="0" />
                        <text class="node-label" y="4">${{nodeId.replace('state', 'S')}}</text>
                    </g>
                `;
            }}

            svg.innerHTML = html;
        }}

        function selectNode(nodeId) {{
            selectedNodeId = nodeId;
            renderGraph();
            renderDetail(nodeId);
        }}

        // =====================================================================
        // Action Panel Functions
        // =====================================================================

        function toggleActionPanel(actionName) {{
            if (selectedActionName === actionName) {{
                hideActionPanel();
            }} else {{
                showActionPanel(actionName);
            }}
        }}

        function showActionPanel(actionName) {{
            selectedActionName = actionName;
            selectedLabelType = null;  // Clear label selection
            const panel = document.getElementById('action-panel');
            const title = document.getElementById('action-panel-title');
            const content = document.getElementById('action-panel-content');

            title.textContent = `Action: ${{actionName}}`;

            // Get action definition from treeData
            const actionDef = treeData.action_definitions?.[actionName];
            content.innerHTML = renderActionDefinition(actionDef);

            panel.classList.add('visible');
            renderGraph();  // Re-render to update selected state
        }}

        function hideActionPanel() {{
            selectedActionName = null;
            selectedLabelType = null;
            const panel = document.getElementById('action-panel');
            panel.classList.remove('visible');
            renderGraph();  // Re-render to update selected state
        }}

        // Show Solver or Time panel
        function showLabelPanel(labelType) {{
            if (selectedLabelType === labelType) {{
                hideActionPanel();
                return;
            }}

            selectedLabelType = labelType;
            selectedActionName = null;  // Clear action selection
            const panel = document.getElementById('action-panel');
            const title = document.getElementById('action-panel-title');
            const content = document.getElementById('action-panel-content');

            if (labelType === 'solver') {{
                title.textContent = 'Solver Rules';
                const rules = treeData.solver_definitions?.solver?.rules;
                content.innerHTML = rules ? renderSolverRules(rules) :
                    '<p style="color: var(--text-dim);">No solver rules defined</p>';
            }} else if (labelType === 'time') {{
                title.textContent = 'Time Constraints';
                const branches = treeData.constraint_definitions?.constraint?.branches;
                content.innerHTML = branches ? renderConstraintBranches(branches) :
                    '<p style="color: var(--text-dim);">No time constraints defined</p>';
            }}

            panel.classList.add('visible');
            renderGraph();  // Re-render to update selected state
        }}

        function renderActionDefinition(def) {{
            if (!def) {{
                return '<p style="color: var(--text-dim);">No definition available</p>';
            }}

            let html = '';

            // Preconditions
            if (def.preconditions && def.preconditions.length > 0) {{
                html += `
                    <div class="condition-section">
                        <div class="condition-section-title precondition">Preconditions</div>
                        <div class="condition-tree">
                            ${{renderPreconditions(def.preconditions)}}
                        </div>
                    </div>
                `;
            }}

            // Effects
            if (def.effects && def.effects.length > 0) {{
                html += `
                    <div class="condition-section">
                        <div class="condition-section-title effects">Effects</div>
                        <div class="condition-tree">
                            ${{renderEffects(def.effects)}}
                        </div>
                    </div>
                `;
            }}

            if (!html) {{
                html = '<p style="color: var(--text-dim);">No preconditions or effects defined</p>';
            }}

            return html;
        }}

        function renderPreconditions(preconditions) {{
            return preconditions.map(cond => renderCondition(cond, 'precondition')).join('');
        }}

        function renderCondition(cond, context) {{
            if (cond.type === 'or') {{
                const subConds = (cond.conditions || []).map((c, i) => {{
                    const prefix = i === 0 ? '' : '<span class="condition-keyword or">OR</span>';
                    return `${{prefix}}${{renderCondition(c, context)}}`;
                }}).join('');
                return `<div class="condition-block or">${{subConds}}</div>`;
            }} else if (cond.type === 'and') {{
                const subConds = (cond.conditions || []).map((c, i) => {{
                    const prefix = i === 0 ? '' : '<span class="condition-keyword and">AND</span>';
                    return `${{prefix}}${{renderCondition(c, context)}}`;
                }}).join('');
                return `<div class="condition-block and">${{subConds}}</div>`;
            }} else if (cond.type === 'attribute_check') {{
                return renderAttributeCheck(cond);
            }} else {{
                return `<span class="condition-expr">${{cond.description || 'Unknown condition'}}</span>`;
            }}
        }}

        function renderAttributeCheck(cond) {{
            const attr = cond.attribute || '';
            const op = getOperatorSymbol(cond.operator);
            let val = cond.value;
            if (Array.isArray(val)) {{
                val = '{{' + val.join(', ') + '}}';
            }}
            return `
                <span class="condition-expr">
                    <span class="attr">${{attr}}</span>
                    <span class="op">${{op}}</span>
                    <span class="val">${{val}}</span>
                </span>
            `;
        }}

        function renderEffects(effects) {{
            let html = '';
            for (const effect of effects) {{
                if (effect.type === 'conditional') {{
                    html += renderConditionalEffect(effect);
                }} else if (effect.type === 'set_attribute') {{
                    html += renderSetAttributeEffect(effect);
                }} else if (effect.type === 'trend') {{
                    html += renderTrendEffect(effect);
                }} else {{
                    html += `<div class="condition-block">${{effect.description || 'Unknown effect'}}</div>`;
                }}
            }}
            return html;
        }}

        function renderConditionalEffect(effect) {{
            const branchType = effect.branch_type || 'if';
            const keyword = branchType.toUpperCase();
            const keywordClass = branchType.toLowerCase();

            let conditionHtml = '';
            if (effect.condition) {{
                conditionHtml = renderCondition(effect.condition, 'effect');
            }}

            let thenHtml = '';
            if (effect.then_effects && effect.then_effects.length > 0) {{
                thenHtml = effect.then_effects.map(e => {{
                    if (e.type === 'set_attribute') {{
                        return `<div><span class="effect-target">${{e.target}}</span> = ` +
                               `<span class="effect-value">${{e.value}}</span></div>`;
                    }} else if (e.type === 'trend') {{
                        return `<div><span class="effect-target">${{e.target}}</span>.trend = ` +
                               `<span class="effect-value">${{e.direction}}</span></div>`;
                    }}
                    return `<div>${{e.description || 'effect'}}</div>`;
                }}).join('');
            }}

            let elseHtml = '';
            if (effect.else_effects && effect.else_effects.length > 0) {{
                // Check if else contains a conditional (ELIF) or just direct effects (ELSE)
                const hasConditional = effect.else_effects.some(e => e.type === 'conditional');
                if (hasConditional) {{
                    // Render nested conditionals (ELIF chain)
                    elseHtml = effect.else_effects.map(e => {{
                        if (e.type === 'conditional') {{
                            return renderConditionalEffect(e);
                        }} else if (e.type === 'set_attribute') {{
                            return `<div class="condition-block else">
                                <span class="condition-keyword else">ELSE</span>
                                <div class="nested-conditions">
                                    <div><span class="effect-target">${{e.target}}</span> =
                                    <span class="effect-value">${{e.value}}</span></div>
                                </div>
                            </div>`;
                        }} else if (e.type === 'trend') {{
                            return `<div class="condition-block else">
                                <span class="condition-keyword else">ELSE</span>
                                <div class="nested-conditions">
                                    <div><span class="effect-target">${{e.target}}</span>.trend =
                                    <span class="effect-value">${{e.direction}}</span></div>
                                </div>
                            </div>`;
                        }}
                        return '';
                    }}).join('');
                }} else {{
                    // Pure ELSE block with direct effects
                    const elseContent = effect.else_effects.map(e => {{
                        if (e.type === 'set_attribute') {{
                            return `<div><span class="effect-target">${{e.target}}</span> = ` +
                                   `<span class="effect-value">${{e.value}}</span></div>`;
                        }} else if (e.type === 'trend') {{
                            return `<div><span class="effect-target">${{e.target}}</span>.trend = ` +
                                   `<span class="effect-value">${{e.direction}}</span></div>`;
                        }}
                        return `<div>${{e.description || 'effect'}}</div>`;
                    }}).join('');
                    elseHtml = `
                        <div class="condition-block else">
                            <span class="condition-keyword else">ELSE</span>
                            <div class="nested-conditions">${{elseContent}}</div>
                        </div>
                    `;
                }}
            }}

            return `
                <div class="condition-block ${{keywordClass}}">
                    <span class="condition-keyword ${{keywordClass}}">${{keyword}}</span>
                    ${{conditionHtml}}
                    <div class="nested-conditions">${{thenHtml}}</div>
                </div>
                ${{elseHtml}}
            `;
        }}

        function renderSetAttributeEffect(effect) {{
            return `
                <div class="condition-block">
                    <span class="effect-target">${{effect.target}}</span> =
                    <span class="effect-value">${{effect.value}}</span>
                </div>
            `;
        }}

        function renderTrendEffect(effect) {{
            return `
                <div class="condition-block">
                    <span class="effect-target">${{effect.target}}</span>.trend =
                    <span class="effect-value">${{effect.direction}}</span>
                </div>
            `;
        }}

        function renderDetail(nodeId) {{
            const panel = document.getElementById('detail-panel');
            const node = treeData.nodes[nodeId];

            if (!node) {{
                panel.className = 'detail-panel empty';
                panel.innerHTML = `<div class="empty-icon">◉</div><p>Node not found</p>`;
                return;
            }}

            panel.className = 'detail-panel';

            const snapshot = node.snapshot?.object_state || {{}};
            // Filter out debug/internal changes like [CONDITIONAL_EVAL]
            const changes = (node.changes || []).filter(c => {{
                const attr = c.attribute || '';
                return !attr.startsWith('[') && !attr.endsWith(']');
            }});
            const changedAttrs = new Set(changes.map(c => {{
                let attr = c.attribute || '';
                if (attr.endsWith('.trend')) attr = attr.slice(0, -6);
                return attr;
            }}));

            // DAG support: check parent_ids array
            const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
            const isRoot = parentIds.length === 0;
            const isMerged = parentIds.length > 1;
            const status = node.action_status || 'ok';
            const isPruned = node.pruned === true;
            const statusClass = isPruned ? 'failed' : (isRoot ? '' : (status === 'ok' ? 'success' : 'failed'));

            const nodeType = node.node_type || 'action';

            // Determine node type label and color
            let nodeTypeLabel = 'Action';
            let nodeTypeColor = 'var(--accent-green)';
            if (isPruned) {{
                nodeTypeLabel = 'Pruned';
                nodeTypeColor = '#484f58';
            }} else if (nodeType === 'root') {{
                nodeTypeLabel = 'Initial State';
                nodeTypeColor = 'var(--accent-gold)';
            }} else if (nodeType === 'solver') {{
                nodeTypeLabel = 'Solver';
                nodeTypeColor = 'var(--accent-purple)';
            }} else if (nodeType === 'time') {{
                nodeTypeLabel = 'Time';
                nodeTypeColor = 'var(--accent-cyan)';
            }} else if (nodeType === 'constraint') {{
                nodeTypeLabel = 'Constraint';
                nodeTypeColor = 'var(--accent-cyan)';
            }}

            let html = `
                <div class="detail-header">
                    <h2>${{nodeId}}</h2>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span style="background: ${{nodeTypeColor}}; color: #0d1117; padding: 2px 8px;
                                     border-radius: 4px; font-size: 0.75em; font-weight: 600;">
                            ${{nodeTypeLabel}}
                        </span>
                        <div class="action ${{statusClass}}">${{node.action_name || 'Initial State'}}</div>
                    </div>
            `;

            if (node.branch_condition) {{
                const bc = node.branch_condition;
                html += `<div class="branch">${{formatBranchCondition(bc)}}</div>`;
            }}

            if (node.pruned) {{
                html += `<div style="color: #484f58; margin-top: 8px; font-size: 0.9em;">` +
                        `Pruned: ${{node.pruned_reason || 'User resolved uncertainty'}}</div>`;
            }}

            if (node.action_error) {{
                html += `<div style="color: var(--accent-red); margin-top: 8px; ` +
                        `font-size: 0.9em;">${{node.action_error}}</div>`;
            }}

            // Show merged node info
            if (isMerged) {{
                html += `<div style="color: var(--text-dim); margin-top: 8px; ` +
                        `font-size: 0.9em;">Merged node (${{parentIds.length}} parents)</div>`;
            }}

            html += '</div>';

            // SECTION 1: World State (first, collapsed by default)
            html += `
                <div class="section collapsed">
                    <div class="section-title" onclick="toggleSection(this)">World State</div>
                    <div class="section-content">
                    <div class="attr-list" id="attr-list">
            `;

            const parts = snapshot.parts || {{}};
            const globalAttrs = snapshot.global_attributes || {{}};

            const relevantAttrs = [];
            const otherAttrs = [];

            // Helper to check if an attribute is "relevant" (should be highlighted)
            // Relevant = attribute has changes, OR it's the root node (show all)
            const isAttrRelevant = (path) => {{
                if (changedAttrs.size > 0) {{
                    return changedAttrs.has(path);
                }}
                // For root node (no action), show all as relevant
                return isRoot;
            }};

            // Process parts
            for (const [partName, partData] of Object.entries(parts)) {{
                const attrs = partData.attributes || {{}};
                for (const [attrName, attrData] of Object.entries(attrs)) {{
                    const fullPath = `${{partName}}.${{attrName}}`;
                    const isRelevant = isAttrRelevant(fullPath);
                    const entry = {{ path: fullPath, data: attrData, isChanged: isRelevant }};

                    if (isRelevant) {{
                        relevantAttrs.push(entry);
                    }} else {{
                        otherAttrs.push(entry);
                    }}
                }}
            }}

            // Process global attributes
            for (const [attrName, attrData] of Object.entries(globalAttrs)) {{
                const isRelevant = isAttrRelevant(attrName);
                const entry = {{ path: attrName, data: attrData, isChanged: isRelevant }};

                if (isRelevant) {{
                    relevantAttrs.push(entry);
                }} else {{
                    otherAttrs.push(entry);
                }}
            }}

            // Render relevant attributes
            for (const {{ path, data, isChanged }} of relevantAttrs) {{
                html += renderAttrItem(path, data, isChanged, true);
            }}

            html += '</div>';  // close attr-list

            // Other attributes (expandable)
            if (otherAttrs.length > 0) {{
                html += `
                    <div class="expand-btn" onclick="toggleOthers()">
                        Show ${{otherAttrs.length}} other attributes ▼
                    </div>
                    <div class="attr-list hidden" id="other-attrs">
                `;

                for (const {{ path, data }} of otherAttrs) {{
                    html += renderAttrItem(path, data, false, false);
                }}

                html += '</div>';
            }}

            html += '</div></div>';  // close section-content and section (World State)

            // SECTION 2+: Changes sections (collapsed by default)
            if (isMerged) {{
                // Primary parent changes (first parent)
                const primaryParent = parentIds[0];
                const pLabel = primaryParent.replace('state', 'S');
                html += `
                    <div class="section collapsed">
                        <div class="section-title" onclick="toggleSection(this)">` +
                        `Changes from ${{pLabel}}</div>
                        <div class="section-content">
                            <div class="change-list">
                `;
                if (changes.length > 0) {{
                    for (const change of changes) {{
                        html += `
                            <div class="change-item">
                                <span class="attr-name">${{change.attribute}}</span>
                                <span class="change-before">${{formatValue(change.before) || '—'}}</span>
                                <span class="change-arrow">→</span>
                                <span class="change-after">${{formatValue(change.after) || '—'}}</span>
                            </div>
                        `;
                    }}
                }} else {{
                    html += `<div class="change-item" style="color: var(--text-dim);">No changes (same state)</div>`;
                }}
                html += '</div></div></div>';

                // Additional parent changes from incoming_edges
                if (node.incoming_edges && node.incoming_edges.length > 0) {{
                    for (const edge of node.incoming_edges) {{
                        const edgeChanges = (edge.changes || []).filter(c => {{
                            const attr = c.attribute || '';
                            return !attr.startsWith('[') && !attr.endsWith(']');
                        }});
                        if (edgeChanges.length > 0) {{
                            const eLabel = edge.parent_id.replace('state', 'S');
                            html += `
                                <div class="section collapsed">
                                    <div class="section-title" onclick="toggleSection(this)">` +
                                    `Changes from ${{eLabel}}</div>
                                    <div class="section-content">
                                        <div class="change-list">
                            `;
                            for (const change of edgeChanges) {{
                                html += `
                                    <div class="change-item">
                                        <span class="attr-name">${{change.attribute}}</span>
                                        <span class="change-before">${{formatValue(change.before) || '—'}}</span>
                                        <span class="change-arrow">→</span>
                                        <span class="change-after">${{formatValue(change.after) || '—'}}</span>
                                    </div>
                                `;
                            }}
                            html += '</div></div></div>';
                        }}
                    }}
                }}
            }} else if (changes.length > 0) {{
                html += `
                    <div class="section collapsed">
                        <div class="section-title" onclick="toggleSection(this)">Changes</div>
                        <div class="section-content">
                            <div class="change-list">
                `;

                for (const change of changes) {{
                    html += `
                        <div class="change-item">
                            <span class="attr-name">${{change.attribute}}</span>
                            <span class="change-before">${{formatValue(change.before) || '—'}}</span>
                            <span class="change-arrow">→</span>
                            <span class="change-after">${{formatValue(change.after) || '—'}}</span>
                        </div>
                    `;
                }}

                html += '</div></div></div>';
            }}

            panel.innerHTML = html;

            // Restore section states if we have saved states for this node
            if (sectionStates[nodeId]) {{
                const sections = document.querySelectorAll('.section');
                const states = sectionStates[nodeId];
                sections.forEach((s, i) => {{
                    if (i < states.length) {{
                        if (states[i]) {{
                            s.classList.add('collapsed');
                        }} else {{
                            s.classList.remove('collapsed');
                        }}
                    }}
                }});
            }}

            // Restore "other attributes" expanded state
            if (otherAttrsStates[nodeId]) {{
                const el = document.getElementById('other-attrs');
                const btn = document.querySelector('.expand-btn');
                if (el && btn) {{
                    el.classList.remove('hidden');
                    btn.textContent = btn.textContent.replace('▼', '▲');
                }}
            }}
        }}

        function toggleSection(titleEl) {{
            const section = titleEl.parentElement;
            section.classList.toggle('collapsed');
            // Save section state for current node
            if (selectedNodeId) {{
                const sections = document.querySelectorAll('.section');
                const states = [];
                sections.forEach(s => states.push(s.classList.contains('collapsed')));
                sectionStates[selectedNodeId] = states;
            }}
        }}

        function formatValue(value) {{
            // Handle value sets (arrays)
            if (Array.isArray(value)) {{
                return '{{' + value.join(', ') + '}}';
            }}
            return value || '—';
        }}

        function getOperatorSymbol(op) {{
            switch(op) {{
                case 'equals': return '==';
                case 'not_equals': return '!=';
                case 'in': return '∈';
                case 'not_in': return '∉';
                case 'gt': return '>';
                case 'gte': return '>=';
                case 'lt': return '<';
                case 'lte': return '<=';
                default: return op || '==';
            }}
        }}

        // Render solver rules for the detail panel
        function renderSolverRules(rules) {{
            if (!rules || rules.length === 0) return '<p style="color: var(--text-dim);">No rules defined</p>';

            let html = '<div class="solver-rules">';
            for (const rule of rules) {{
                html += `
                    <div style="margin-bottom: 12px; padding: 10px; background: rgba(163, 113, 247, 0.1);
                                border-left: 3px solid var(--accent-purple); border-radius: 4px;">
                        <div style="font-weight: 600; color: var(--accent-purple);">${{rule.name}}</div>
                        <div style="font-size: 0.85em; color: var(--text-dim); margin-top: 4px;">
                            ${{rule.description || ''}}
                        </div>
                `;

                if (rule.condition) {{
                    html += `<div style="margin-top: 8px; font-size: 0.85em;">
                        <span style="color: var(--text-dim);">IF:</span>
                        <span style="color: var(--text);">${{rule.condition.description || 'condition'}}</span>
                    </div>`;
                }}

                if (rule.implies && rule.implies.length > 0) {{
                    html += `<div style="margin-top: 4px; font-size: 0.85em;">
                        <span style="color: var(--accent-green);">THEN:</span>
                    </div>`;
                    for (const effect of rule.implies) {{
                        html += `<div style="margin-left: 16px; font-size: 0.85em;">
                            <span style="color: var(--text);">${{effect.target}} = ${{effect.value}}</span>
                        </div>`;
                    }}
                }}

                // For simple rules with condition/implies/otherwise (no cases)
                if (rule.otherwise && rule.otherwise.length > 0 && (!rule.cases || rule.cases.length === 0)) {{
                    html += `<div style="margin-top: 4px; font-size: 0.85em;">
                        <span style="color: var(--accent-red);">ELSE:</span>
                    </div>`;
                    for (const effect of rule.otherwise) {{
                        html += `<div style="margin-left: 16px; font-size: 0.85em;">
                            <span style="color: var(--text);">${{effect.target}} = ${{effect.value}}</span>
                        </div>`;
                    }}
                }}

                // For case-based rules: show cases first, then otherwise
                if (rule.cases && rule.cases.length > 0) {{
                    html += '<div style="margin-top: 8px; font-size: 0.85em;">';
                    for (let i = 0; i < rule.cases.length; i++) {{
                        const c = rule.cases[i];
                        const label = i === 0 ? 'IF' : 'ELIF';
                        html += `<div style="margin-top: 4px;">
                            <span style="color: var(--accent-gold);">${{label}}:</span>
                            <span style="color: var(--text);">${{c.condition?.description || 'condition'}}</span>
                        </div>`;
                        html += `<div style="margin-left: 16px;">
                            <span style="color: var(--accent-green);">THEN:</span>
                        </div>`;
                        for (const effect of c.implies || []) {{
                            html += `<div style="margin-left: 32px;">
                                <span style="color: var(--text);">${{effect.target}} = ${{effect.value}}</span>
                            </div>`;
                        }}
                    }}
                    // Show otherwise AFTER cases
                    if (rule.otherwise && rule.otherwise.length > 0) {{
                        html += `<div style="margin-top: 4px;">
                            <span style="color: var(--accent-red);">ELSE:</span>
                        </div>`;
                        html += `<div style="margin-left: 16px;">
                            <span style="color: var(--accent-green);">THEN:</span>
                        </div>`;
                        for (const effect of rule.otherwise) {{
                            html += `<div style="margin-left: 32px;">
                                <span style="color: var(--text);">${{effect.target}} = ${{effect.value}}</span>
                            </div>`;
                        }}
                    }}
                    html += '</div>';
                }}

                html += '</div>';
            }}
            html += '</div>';
            return html;
        }}

        // Render constraint branches for the detail panel
        function renderConstraintBranches(branches) {{
            if (!branches || branches.length === 0) return '<p style="color: var(--text-dim);">No constraints</p>';

            // Known space complements for resolving negated values
            const spaceComplements = {{
                // binary_state: off, on
                'off': 'on',
                'on': 'off',
                // brightness_level: none, low, medium, high
                'none': '{{low, medium, high}}',
                'low': '{{none, medium, high}}',
                'medium': '{{none, low, high}}',
                'high': '{{none, low, medium}}',
                // battery_level: empty, low, medium, high, full
                'empty': '{{low, medium, high, full}}',
                'full': '{{empty, low, medium, high}}',
            }};

            // Helper to format values - resolve negated values to actual valid values
            function formatValue(val) {{
                if (typeof val === 'string' && val.startsWith('!')) {{
                    const excluded = val.slice(1);
                    // Look up the complement in known spaces
                    if (spaceComplements[excluded]) {{
                        return spaceComplements[excluded];
                    }}
                    // Fallback to "not X" if unknown
                    return `not ${{excluded}}`;
                }}
                return val;
            }}

            let html = '<div class="constraint-branches">';

            // Add explanation header
            html += `<p style="color: var(--text-dim); font-size: 0.85em; margin-bottom: 12px;">
                Time constraints define what states are possible when time passes and values change due to trends.
                They ensure the world stays consistent over time.
            </p>`;

            for (const branch of branches) {{
                html += `
                    <div style="margin-bottom: 12px; padding: 10px; background: rgba(88, 166, 255, 0.1);
                                border-left: 3px solid var(--accent-cyan); border-radius: 4px;">
                `;

                if (branch.condition) {{
                    html += `<div style="font-size: 0.85em;">
                        <span style="color: var(--accent-gold);">IF:</span>
                        <span style="color: var(--text);">${{branch.condition.description || 'condition'}}</span>
                    </div>`;
                }}

                if (branch.effects && branch.effects.length > 0) {{
                    html += `<div style="margin-top: 4px; margin-left: 16px; font-size: 0.85em;">
                        <span style="color: var(--accent-green);">THEN:</span>
                    </div>`;
                    for (const effect of branch.effects) {{
                        html += `<div style="margin-left: 32px; font-size: 0.85em;">
                            <span style="color: var(--text);">${{effect.target}} = ${{formatValue(effect.value)}}</span>
                        </div>`;
                    }}
                }}

                // Render elif_cases
                if (branch.elif_cases && branch.elif_cases.length > 0) {{
                    for (const elifCase of branch.elif_cases) {{
                        html += `<div style="margin-top: 4px; font-size: 0.85em;">
                            <span style="color: var(--accent-gold);">ELIF:</span>
                            <span style="color: var(--text);">${{elifCase.condition?.description || 'condition'}}</span>
                        </div>`;
                        if (elifCase.effects && elifCase.effects.length > 0) {{
                            html += `<div style="margin-left: 16px; font-size: 0.85em;">
                                <span style="color: var(--accent-green);">THEN:</span>
                            </div>`;
                            for (const effect of elifCase.effects) {{
                                const fv = formatValue(effect.value);
                                html += `<div style="margin-left: 32px; font-size: 0.85em;">
                                    <span style="color: var(--text);">${{effect.target}} = ${{fv}}</span>
                                </div>`;
                            }}
                        }}
                    }}
                }}

                if (branch.else_effects && branch.else_effects.length > 0) {{
                    html += `<div style="margin-top: 4px; font-size: 0.85em;">
                        <span style="color: var(--accent-red);">ELSE:</span>
                    </div>`;
                    html += `<div style="margin-left: 16px; font-size: 0.85em;">
                        <span style="color: var(--accent-green);">THEN:</span>
                    </div>`;
                    for (const effect of branch.else_effects) {{
                        html += `<div style="margin-left: 32px; font-size: 0.85em;">
                            <span style="color: var(--text);">${{effect.target}} = ${{formatValue(effect.value)}}</span>
                        </div>`;
                    }}
                }}

                html += '</div>';
            }}
            html += '</div>';
            return html;
        }}

        function formatBranchCondition(bc) {{
            // Handle compound conditions (AND/OR)
            if (bc.compound_type && bc.sub_conditions && bc.sub_conditions.length > 0) {{
                const connectorText = bc.compound_type === 'and' ? 'AND' : 'OR';
                const connector = `<span class="compound-connector">${{connectorText}}</span>`;
                const parts = bc.sub_conditions.map(sub => formatBranchCondition(sub));
                return parts.join(' ' + connector + ' ');
            }}

            // Simple condition
            const attr = bc.attribute || '';
            let op = getOperatorSymbol(bc.operator);
            // Check if value is a set with MORE than one element
            const isMultiValueSet = Array.isArray(bc.value) && bc.value.length > 1;
            const isSingleValueArray = Array.isArray(bc.value) && bc.value.length === 1;

            // If value is a multi-value set and operator is equals/not_equals, use ∈/∉ instead
            if (isMultiValueSet) {{
                if (bc.operator === 'equals' || bc.operator === 'in') {{
                    op = '∈';
                }} else if (bc.operator === 'not_equals' || bc.operator === 'not_in') {{
                    op = '∉';
                }}
            }}

            // Determine value display
            let valueDisplay;
            if (isMultiValueSet) {{
                valueDisplay = '{{' + bc.value.join(', ') + '}}';
            }} else if (isSingleValueArray) {{
                // Single-item array: unwrap and display as single value
                valueDisplay = bc.value[0] || '';
            }} else {{
                valueDisplay = bc.value || '';
            }}

            if (!attr && !valueDisplay) {{
                return bc.branch_type || '';
            }}

            // Format with color classes
            const attrHtml = `<span class="attr-name">${{attr}}</span>`;
            const opHtml = `<span class="operator">${{op}}</span>`;
            const valueHtml = `<span class="value-set">${{valueDisplay}}</span>`;

            return `${{attrHtml}} ${{opHtml}} ${{valueHtml}}`;
        }}

        function isValueSet(value) {{
            return Array.isArray(value) && value.length > 1;
        }}

        function renderAttrItem(path, data, isChanged, isRelevant) {{
            const itemClass = isChanged ? 'changed' : (isRelevant ? 'relevant' : '');

            let trendHtml = '';
            if (data.trend && data.trend !== 'none') {{
                const trendClass = data.trend === 'up' ? 'up' : 'down';
                const trendIcon = data.trend === 'up' ? '↑' : '↓';
                trendHtml = `<span class="trend ${{trendClass}}">${{trendIcon}} ${{data.trend}}</span>`;
            }}

            // Add value set indicator if the value is a set
            let valueSetClass = '';
            let displayValue = formatValue(data.value);
            if (isValueSet(data.value)) {{
                valueSetClass = 'value-set';
            }}

            return `
                <div class="attr-item ${{itemClass}}">
                    <span class="attr-name">${{path}}</span>
                    <div class="attr-value">
                        <span class="value ${{valueSetClass}}">${{displayValue}}</span>
                        ${{trendHtml}}
                    </div>
                </div>
            `;
        }}

        function toggleOthers() {{
            const el = document.getElementById('other-attrs');
            const btn = document.querySelector('.expand-btn');
            el.classList.toggle('hidden');

            if (el.classList.contains('hidden')) {{
                btn.textContent = btn.textContent.replace('▲', '▼');
            }} else {{
                btn.textContent = btn.textContent.replace('▼', '▲');
            }}

            // Save state for current node
            if (selectedNodeId) {{
                otherAttrsStates[selectedNodeId] = !el.classList.contains('hidden');
            }}
        }}

        function showTooltip(event, nodeId) {{
            const node = treeData.nodes[nodeId];
            if (!node) return;

            const tooltip = document.getElementById('tooltip');
            const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
            const isMerged = parentIds.length > 1;

            let mergedHint = '';
            if (isMerged) {{
                mergedHint = `<div style="color: var(--text-dim);">Merged (${{parentIds.length}} parents)</div>`;
            }}

            tooltip.innerHTML = `
                <div class="tooltip-title">${{nodeId}}</div>
                <div class="tooltip-action">${{node.action_name || 'Initial State'}}</div>
                ${{mergedHint}}
                <div class="tooltip-hint">Click to view details</div>
            `;

            const rect = event.target.getBoundingClientRect();
            const containerRect = document.querySelector('.graph-container').getBoundingClientRect();

            tooltip.style.left = (rect.right - containerRect.left + 10) + 'px';
            tooltip.style.top = (rect.top - containerRect.top) + 'px';
            tooltip.classList.add('visible');
        }}

        function hideTooltip() {{
            document.getElementById('tooltip').classList.remove('visible');
        }}

        // Initialize: collapse all action instances by default
        // When collapsed: shows solver boundary nodes (purple) instead of action nodes (green)
        // Users can click action labels (+) to expand and see the action nodes
        function initializeCollapsedActions() {{
            const actionSequence = treeData.actions || [];
            for (let i = 0; i < actionSequence.length; i++) {{
                collapsedActionIndices.add(i);
            }}
        }}
        initializeCollapsedActions();

        // Initial render
        renderGraph();

        // Auto-select root
        if (treeData.root_id) {{
            selectNode(treeData.root_id);
        }}
    </script>
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
