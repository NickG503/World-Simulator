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
        </header>

        <div class="graph-container">
            <svg id="graph"></svg>
            <div class="tooltip" id="tooltip"></div>
        </div>

        <div class="detail-panel empty" id="detail-panel">
            <div class="empty-icon">◉</div>
            <p>Click a node to view details</p>
        </div>
    </div>

    <script>
        const treeData = {tree_json};

        let selectedNodeId = null;
        const sectionStates = {{}};  // Track collapsed state per node
        const otherAttrsStates = {{}};  // Track "other attributes" expanded state per node
        const NODE_RADIUS = 28;
        const LEVEL_HEIGHT = 120;
        const NODE_SPACING = 80;
        const MIN_SIBLING_SPACING = 20;

        // Calculate tree layout using proper hierarchical algorithm
        // This groups children under their parent and centers parents over children
        function calculateLayout() {{
            const nodes = treeData.nodes || {{}};
            const rootId = treeData.root_id;
            const layout = {{}};

            // Build adjacency list
            const children = {{}};
            for (const [id, node] of Object.entries(nodes)) {{
                children[id] = node.children_ids || [];
            }}

            // Calculate depth (level) for each node
            const depths = {{}};
            function calcDepth(nodeId, depth) {{
                depths[nodeId] = depth;
                for (const childId of children[nodeId] || []) {{
                    calcDepth(childId, depth + 1);
                }}
            }}
            calcDepth(rootId, 0);

            // Calculate subtree width for each node (bottom-up)
            const subtreeWidth = {{}};
            function calcWidth(nodeId) {{
                const kids = children[nodeId] || [];
                if (kids.length === 0) {{
                    subtreeWidth[nodeId] = NODE_SPACING;
                    return NODE_SPACING;
                }}
                let totalWidth = 0;
                for (const childId of kids) {{
                    totalWidth += calcWidth(childId);
                }}
                // Add spacing between siblings
                totalWidth += (kids.length - 1) * MIN_SIBLING_SPACING;
                subtreeWidth[nodeId] = Math.max(NODE_SPACING, totalWidth);
                return subtreeWidth[nodeId];
            }}
            calcWidth(rootId);

            // Assign x positions (top-down), centering parent over children
            let maxWidth = 0;
            function assignX(nodeId, leftX) {{
                const kids = children[nodeId] || [];
                const width = subtreeWidth[nodeId];

                if (kids.length === 0) {{
                    // Leaf node: center in its allocated space
                    layout[nodeId] = {{ x: leftX + width / 2 }};
                }} else {{
                    // Internal node: place children, then center self
                    let childX = leftX;
                    let firstChildCenter = 0;
                    let lastChildCenter = 0;

                    kids.forEach((childId, idx) => {{
                        assignX(childId, childX);
                        if (idx === 0) firstChildCenter = layout[childId].x;
                        if (idx === kids.length - 1) lastChildCenter = layout[childId].x;
                        childX += subtreeWidth[childId] + MIN_SIBLING_SPACING;
                    }});

                    // Center parent over children
                    layout[nodeId] = {{ x: (firstChildCenter + lastChildCenter) / 2 }};
                }}

                maxWidth = Math.max(maxWidth, Math.abs(layout[nodeId].x));
            }}

            // Start from center (negative half of root subtree width)
            const rootWidth = subtreeWidth[rootId];
            assignX(rootId, -rootWidth / 2);

            // Assign y positions based on depth
            let maxLevel = 0;
            for (const [nodeId, depth] of Object.entries(depths)) {{
                layout[nodeId].y = depth * LEVEL_HEIGHT + NODE_RADIUS + 40;
                maxLevel = Math.max(maxLevel, depth);
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

            // Track which actions we've labeled per level (to avoid duplicates)
            const levelActions = {{}};

            // Draw edges first (so they're behind nodes)
            // For DAG support, we draw edges from parent to child by iterating children
            // and checking parent_ids (which may contain multiple parents for merged nodes)
            const nodes = treeData.nodes || {{}};

            for (const [nodeId, node] of Object.entries(nodes)) {{
                const pos = layout[nodeId];
                if (!pos) continue;

                for (const childId of node.children_ids || []) {{
                    const childPos = layout[childId];
                    if (!childPos) continue;

                    // Curved path - all edges use same style
                    const midY = (pos.y + childPos.y) / 2;
                    const pathD = `M${{pos.x}},${{pos.y + NODE_RADIUS}} ` +
                                  `Q${{pos.x}},${{midY}} ${{childPos.x}},${{childPos.y - NODE_RADIUS}}`;
                    html += `<path class="edge" d="${{pathD}}" />`;

                    // Track action for this level transition (only label once per level)
                    const childNode = nodes[childId];
                    if (childNode && childNode.action_name) {{
                        const levelKey = Math.round(childPos.y);
                        if (!levelActions[levelKey]) {{
                            levelActions[levelKey] = {{
                                action: childNode.action_name,
                                y: midY,
                                hasFailure: childNode.action_status !== 'ok'
                            }};
                        }} else if (childNode.action_status !== 'ok') {{
                            levelActions[levelKey].hasFailure = true;
                        }}
                    }}
                }}
            }}

            // Draw action labels on the left side (once per level)
            const leftX = -width / 2 + 60;
            for (const [levelY, info] of Object.entries(levelActions)) {{
                const labelClass = info.hasFailure ? 'level-action has-failure' : 'level-action';
                const txt = `<text class="${{labelClass}}" x="${{leftX}}" y="${{info.y}}" ` +
                    `text-anchor="start">${{info.action}}</text>`;
                html += txt;
            }}

            // Draw nodes
            for (const [nodeId, node] of Object.entries(nodes)) {{
                const pos = layout[nodeId];
                if (!pos) continue;

                // DAG support: check parent_ids array
                const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
                const isRoot = parentIds.length === 0;
                const isSelected = nodeId === selectedNodeId;
                const status = node.action_status || 'ok';
                const statusClass = isRoot ? 'root' : (status === 'ok' ? 'success' : 'failed');

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
            const statusClass = isRoot ? '' : (status === 'ok' ? 'success' : 'failed');

            let html = `
                <div class="detail-header">
                    <h2>${{nodeId}}</h2>
                    <div class="action ${{statusClass}}">${{node.action_name || 'Initial State'}}</div>
            `;

            if (node.branch_condition) {{
                const bc = node.branch_condition;
                html += `<div class="branch">${{formatBranchCondition(bc)}}</div>`;
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
                if (changes.length > 0) {{
                    const primaryParent = parentIds[0];
                    const pLabel = primaryParent.replace('state', 'S');
                    html += `
                        <div class="section collapsed">
                            <div class="section-title" onclick="toggleSection(this)">` +
                            `Changes from ${{pLabel}}</div>
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
