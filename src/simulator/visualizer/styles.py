"""CSS styles for the simulation tree visualization."""

CSS_STYLES = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
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
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg-dark);
    color: var(--text);
    min-height: 100vh;
    overflow: hidden;
}

.container {
    display: grid;
    grid-template-columns: 1fr 400px;
    grid-template-rows: auto 1fr;
    height: 100vh;
}

header {
    grid-column: 1 / -1;
    padding: 16px 24px;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 24px;
}

.logo {
    font-size: 1.5em;
    font-weight: 600;
    background: linear-gradient(135deg, var(--accent-cyan), var(--accent-green));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.meta {
    color: var(--text-dim);
    font-size: 0.9em;
    display: flex;
    gap: 20px;
}

.meta span {
    display: flex;
    align-items: center;
    gap: 6px;
}

.cli-command {
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
}

.cli-command::before {
    content: '$ ';
    color: var(--accent-green);
}

.header-controls {
    display: flex;
    gap: 12px;
    margin-left: auto;
}

.toggle-btn {
    padding: 6px 12px;
    background: var(--bg-dark);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.85em;
    transition: all 0.2s ease;
}

.toggle-btn:hover {
    border-color: var(--accent-cyan);
    color: var(--text);
}

.toggle-btn.active {
    border-color: var(--accent-purple);
    color: var(--accent-purple);
    background: rgba(163, 113, 247, 0.1);
}

/* Layer legend */
.layer-legend {
    display: flex;
    gap: 16px;
    padding: 8px 16px;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 6px;
    font-size: 0.8em;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
}

.legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid;
}

.legend-dot.action { border-color: var(--accent-green); }
.legend-dot.solver { border-color: var(--accent-purple); }
.legend-dot.time { border-color: var(--accent-cyan); }
.legend-dot.pruned { border-color: #484f58; opacity: 0.5; }

.graph-container {
    position: relative;
    overflow: auto;
    background:
        radial-gradient(circle at 50% 50%, rgba(88, 166, 255, 0.03) 0%, transparent 50%),
        var(--bg-dark);
}

#graph {
    min-width: 100%;
    min-height: 100%;
}

.detail-panel {
    background: var(--bg-card);
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 20px;
}

.detail-panel.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: var(--text-dim);
}

.empty-icon {
    font-size: 4em;
    margin-bottom: 16px;
    opacity: 0.3;
}

.detail-header {
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
}

.detail-header h2 {
    font-size: 1.2em;
    color: var(--accent-cyan);
    margin-bottom: 8px;
}

.detail-header .action {
    font-size: 1.1em;
    color: var(--text);
}

.detail-header .action.success {
    color: var(--accent-green);
}

.detail-header .action.failed {
    color: var(--accent-red);
}

.detail-header .branch {
    color: var(--text-dim);
    font-size: 0.9em;
    margin-top: 6px;
    line-height: 1.5;
}

.detail-header .branch .compound-connector {
    color: var(--accent-purple);
    font-weight: 600;
    padding: 0 4px;
}

.detail-header .branch .attr-name {
    color: var(--accent-blue);
}

.detail-header .branch .operator {
    color: var(--accent-yellow);
    padding: 0 2px;
}

.detail-header .branch .value-set {
    color: var(--accent-cyan);
}

.section {
    margin-bottom: 24px;
}

.section-title {
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
}

.section-title:hover {
    color: var(--text);
}

.section-title::before {
    content: '';
    width: 3px;
    height: 14px;
    background: var(--accent-cyan);
    border-radius: 2px;
}

.section-title::after {
    content: '▼';
    margin-left: auto;
    font-size: 0.7em;
    transition: transform 0.2s ease;
}

.section.collapsed .section-title::after {
    transform: rotate(-90deg);
}

.section.collapsed .section-content {
    display: none;
}

.section-content {
    transition: max-height 0.2s ease;
}

.attr-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attr-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    border: 1px solid transparent;
}

.attr-item.changed {
    border-color: var(--accent-gold);
    background: rgba(210, 153, 34, 0.1);
}

.attr-item.relevant {
    border-color: var(--accent-green);
    background: rgba(63, 185, 80, 0.1);
}

.attr-name {
    color: var(--text-dim);
    font-size: 0.9em;
}

.attr-value {
    display: flex;
    align-items: center;
    gap: 8px;
}

.value {
    font-weight: 500;
    color: var(--text);
    padding: 2px 8px;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 4px;
}

.trend {
    font-size: 0.8em;
    padding: 2px 6px;
    border-radius: 3px;
}

.trend.up {
    color: var(--accent-green);
    background: rgba(63, 185, 80, 0.2);
}

.trend.down {
    color: var(--accent-red);
    background: rgba(248, 81, 73, 0.2);
}

.value.value-set {
    background: rgba(163, 113, 247, 0.2);
    border: 1px solid var(--accent-purple);
    color: var(--accent-purple);
}

.branch-value-set {
    color: var(--accent-purple);
}

.change-item {
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    gap: 8px;
    align-items: center;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    margin-bottom: 6px;
}

.change-before {
    color: var(--text-dim);
    text-decoration: line-through;
}

.change-arrow {
    color: var(--accent-gold);
}

.change-after {
    color: var(--accent-green);
    font-weight: 500;
}

.expand-btn {
    color: var(--accent-cyan);
    cursor: pointer;
    font-size: 0.85em;
    margin-top: 8px;
}

.expand-btn:hover {
    text-decoration: underline;
}

.hidden {
    display: none !important;
}

/* SVG Styles */
.node {
    cursor: pointer;
}

.node-circle {
    stroke-width: 3;
    transition: stroke-width 0.15s ease, filter 0.15s ease;
}

.node:hover .node-circle {
    stroke-width: 5;
    filter: drop-shadow(0 0 6px currentColor);
}

.node.root .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-gold);
}

.node.success .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-green);
}

.node.failed .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-red);
}

.node.solver .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-purple);
}

.node.time .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-cyan);
}

.node.constraint .node-circle {
    fill: var(--bg-card);
    stroke: var(--accent-cyan);
}

.node.pruned .node-circle {
    fill: var(--bg-card);
    stroke: #484f58;
    opacity: 0.35;
}

.node.pruned .node-label {
    opacity: 0.35;
}

.node.selected .node-circle {
    stroke-width: 4;
    filter: drop-shadow(0 0 8px currentColor);
}

.node-label {
    font-family: inherit;
    font-size: 11px;
    fill: var(--text);
    text-anchor: middle;
    pointer-events: none;
}


.edge {
    stroke: var(--border);
    stroke-width: 2;
    fill: none;
}

.edge.active {
    stroke: var(--accent-cyan);
    stroke-width: 3;
}

.edge.pruned-edge {
    stroke: #484f58;
    opacity: 0.25;
    stroke-dasharray: 4 3;
}


/* Action label on the left side per level */
.level-action {
    font-size: 13px;
    fill: var(--text);
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}

/* Tooltip */
.tooltip {
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
}

.tooltip.visible {
    opacity: 1;
}

.tooltip-title {
    font-weight: 600;
    color: var(--accent-cyan);
    margin-bottom: 4px;
}

.tooltip-action {
    color: var(--text);
}

.tooltip-hint {
    color: var(--text-dim);
    font-size: 0.85em;
    margin-top: 8px;
}

/* Action Detail Panel */
.action-panel {
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease, padding 0.3s ease;
    padding: 0 20px;
}

.action-panel.visible {
    max-height: 400px;
    padding: 16px 20px;
    overflow-y: auto;
}

.action-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.action-panel-header h3 {
    font-size: 1.1em;
    color: var(--accent-purple);
    margin: 0;
}

.action-panel-close {
    cursor: pointer;
    color: var(--text-dim);
    font-size: 1.2em;
    padding: 4px 8px;
    border-radius: 4px;
    transition: background 0.2s;
}

.action-panel-close:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text);
}

.condition-section {
    margin-bottom: 16px;
}

.condition-section-title {
    font-size: 0.75em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}

.condition-section-title::before {
    content: '';
    width: 3px;
    height: 12px;
    border-radius: 2px;
}

.condition-section-title.precondition::before {
    background: var(--accent-cyan);
}

.condition-section-title.effects::before {
    background: var(--accent-green);
}

.condition-tree {
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
    font-size: 0.85em;
    line-height: 1.6;
}

.condition-block {
    padding: 8px 12px;
    border-left: 3px solid var(--border);
    background: rgba(255, 255, 255, 0.02);
    margin: 4px 0;
    border-radius: 0 4px 4px 0;
}

.condition-block.if {
    border-left-color: var(--accent-green);
}

.condition-block.elif {
    border-left-color: var(--accent-gold);
}

.condition-block.else {
    border-left-color: var(--accent-red);
}

.condition-block.or {
    border-left-color: var(--accent-purple);
}

.condition-block.and {
    border-left-color: var(--accent-cyan);
}

.condition-keyword {
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.85em;
    margin-right: 8px;
}

.condition-keyword.if { color: var(--accent-green); }
.condition-keyword.elif { color: var(--accent-gold); }
.condition-keyword.else { color: var(--accent-red); }
.condition-keyword.or { color: var(--accent-purple); }
.condition-keyword.and { color: var(--accent-cyan); }

.condition-expr {
    color: var(--text);
}

.condition-expr .attr {
    color: var(--accent-cyan);
}

.condition-expr .op {
    color: var(--accent-gold);
    padding: 0 4px;
}

.condition-expr .val {
    color: var(--accent-green);
}

.effect-arrow {
    color: var(--accent-purple);
    margin: 0 4px;
}

.effect-target {
    color: var(--accent-cyan);
}

.effect-value {
    color: var(--accent-green);
}

.nested-conditions {
    margin-left: 16px;
    padding-left: 8px;
    border-left: 1px dashed var(--border);
}

/* Make action labels clickable */
.level-action {
    cursor: pointer;
    transition: fill 0.2s;
}

.level-action:hover {
    fill: var(--accent-purple);
}

.level-action.selected {
    fill: var(--accent-purple);
    font-weight: 700;
}
"""
