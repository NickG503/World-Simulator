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
    --accent-blue: #79c0ff;
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

.attr-value .value {
    color: var(--accent-green);
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.9em;
}

.attr-value .value.value-set {
    color: var(--accent-cyan);
}

.attr-value .trend {
    font-size: 0.8em;
    padding: 2px 6px;
    border-radius: 4px;
}

.attr-value .trend.up {
    color: var(--accent-red);
    background: rgba(248, 81, 73, 0.15);
}

.attr-value .trend.down {
    color: var(--accent-green);
    background: rgba(63, 185, 80, 0.15);
}

.change-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    border: 1px solid var(--accent-gold);
    background: rgba(210, 153, 34, 0.1);
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.85em;
}

.change-attr {
    color: var(--text-dim);
}

.change-arrow {
    color: var(--accent-gold);
}

.change-before {
    color: var(--accent-red);
    text-decoration: line-through;
    opacity: 0.7;
}

.change-after {
    color: var(--accent-green);
}

.error-box {
    padding: 12px;
    background: rgba(248, 81, 73, 0.1);
    border: 1px solid var(--accent-red);
    border-radius: 6px;
    color: var(--accent-red);
    font-size: 0.9em;
}

.expand-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85em;
    width: 100%;
    text-align: left;
    transition: all 0.2s;
}

.expand-btn:hover {
    border-color: var(--accent-cyan);
    color: var(--text);
}

.hidden {
    display: none;
}

.tooltip {
    position: absolute;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    z-index: 1000;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
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
    font-size: 0.9em;
}

.tooltip-hint {
    color: var(--text-dim);
    font-size: 0.8em;
    margin-top: 8px;
}

.action-panel {
    background: var(--bg-card);
    border-left: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 16px 20px;
    display: none;
    max-height: 50%;
    overflow-y: auto;
}

.action-panel.visible {
    display: block;
}

.action-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}

.action-panel-header h3 {
    color: var(--accent-purple);
    font-size: 1.1em;
}

.action-panel-close {
    cursor: pointer;
    color: var(--text-dim);
    font-size: 1.2em;
    padding: 4px;
}

.action-panel-close:hover {
    color: var(--text);
}

.action-section {
    margin-bottom: 16px;
}

.action-section-title {
    color: var(--text-dim);
    font-size: 0.8em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}

.precondition-list, .postcondition-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.condition-item {
    padding: 8px 10px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
    font-size: 0.85em;
}

.condition-item .attr {
    color: var(--accent-cyan);
}

.condition-item .op {
    color: var(--accent-gold);
    padding: 0 4px;
}

.condition-item .val {
    color: var(--accent-green);
}

.postcondition-item {
    padding: 8px 10px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
    font-size: 0.85em;
    margin-bottom: 6px;
}

.postcondition-item .keyword {
    color: var(--accent-purple);
    font-weight: 600;
}

.postcondition-item .condition {
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
