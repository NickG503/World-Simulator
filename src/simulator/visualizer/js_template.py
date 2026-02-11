"""JavaScript template for the simulation tree visualization."""

JS_TEMPLATE = """
const treeData = __TREE_JSON__;

let selectedNodeId = null;
let selectedActionName = null;
let selectedLabelType = null;  // 'solver' or 'time'
const sectionStates = {};  // Track collapsed state per node
const otherAttrsStates = {};  // Track "other attributes" expanded state per node
const collapsedActionIndices = new Set();  // Track which action INDICES (instances) are collapsed
const NODE_RADIUS = 28;
const LEVEL_HEIGHT = 100;        // Vertical distance between levels
const NODE_SPACING = 70;         // Minimum space between node centers

// Build a map from action node IDs to their instance index in the action sequence
// This allows distinguishing between multiple occurrences of the same action name
const actionNodeToIndex = {};
const actionIndexToNodes = {};

function buildActionInstanceMaps() {
    const nodes = treeData.nodes || {};
    const actionSequence = treeData.actions || [];

    // For each action in sequence, find which action nodes belong to it
    // Action nodes belong to an instance if they match the name AND come in the right order
    const actionCounts = {};  // Track how many times each action name has been seen

    // First, collect all action nodes and their depths
    const actionNodes = [];
    for (const [nodeId, node] of Object.entries(nodes)) {
        if (node.node_type === 'action' && node.action_name) {
            // Calculate depth by walking up to root
            let depth = 0;
            let currentId = nodeId;
            const visited = new Set();
            while (currentId && !visited.has(currentId)) {
                visited.add(currentId);
                const n = nodes[currentId];
                if (!n) break;
                if (n.node_type === 'root') break;
                const parents = n.parent_ids || [];
                if (parents.length > 0) {
                    currentId = parents[0];
                    depth++;
                } else {
                    break;
                }
            }
            actionNodes.push({ nodeId, node, depth, actionName: node.action_name });
        }
    }

    // Sort by depth to process in order
    actionNodes.sort((a, b) => a.depth - b.depth);

    // Now assign each action node to an instance index based on depth and sequence
    // Group by depth first
    const byDepth = {};
    for (const an of actionNodes) {
        if (!byDepth[an.depth]) byDepth[an.depth] = [];
        byDepth[an.depth].push(an);
    }

    // For each depth level, assign instance indices
    // Assumption: at each depth, all action nodes with the same name belong to the same instance
    const depths = Object.keys(byDepth).map(Number).sort((a, b) => a - b);
    let currentSequenceIdx = 0;

    for (const depth of depths) {
        const nodesAtDepth = byDepth[depth];
        // Get unique action names at this depth
        const namesAtDepth = [...new Set(nodesAtDepth.map(n => n.actionName))];

        for (const name of namesAtDepth) {
            // Find which instance index this corresponds to
            // It should be the next occurrence of this name in the sequence
            while (currentSequenceIdx < actionSequence.length &&
                   actionSequence[currentSequenceIdx] !== name) {
                currentSequenceIdx++;
            }

            if (currentSequenceIdx < actionSequence.length) {
                // Assign all nodes with this name at this depth to this instance
                for (const an of nodesAtDepth) {
                    if (an.actionName === name) {
                        actionNodeToIndex[an.nodeId] = currentSequenceIdx;
                        if (!actionIndexToNodes[currentSequenceIdx]) {
                            actionIndexToNodes[currentSequenceIdx] = [];
                        }
                        actionIndexToNodes[currentSequenceIdx].push(an.nodeId);
                    }
                }
                currentSequenceIdx++;
            }
        }
    }
}
buildActionInstanceMaps();

// Toggle collapse state for an action by INDEX
function toggleActionCollapse(actionIndex) {
    if (collapsedActionIndices.has(actionIndex)) {
        collapsedActionIndices.delete(actionIndex);
    } else {
        collapsedActionIndices.add(actionIndex);
    }
    renderGraph();
}

// Check if a node is an intermediate layer (solver/time)
function isIntermediateNode(node) {
    const nodeType = node.node_type || 'action';
    return nodeType === 'solver' || nodeType === 'time' || nodeType === 'constraint';
}

// Find the action instance INDEX that this node belongs to
function findParentActionIndex(nodeId) {
    const nodes = treeData.nodes || {};
    const visited = new Set();

    function search(currentId) {
        if (visited.has(currentId)) return null;
        visited.add(currentId);

        const node = nodes[currentId];
        if (!node) return null;

        // If this is an action node, return its instance index
        if (node.node_type === 'action' && actionNodeToIndex[currentId] !== undefined) {
            return actionNodeToIndex[currentId];
        }

        // If root, stop
        if (node.node_type === 'root') return null;

        // Look at parents
        const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
        for (const parentId of parentIds) {
            const result = search(parentId);
            if (result !== null) return result;
        }
        return null;
    }

    return search(nodeId);
}

// Find the action name that this intermediate node belongs to (for display purposes)
function findParentActionName(nodeId) {
    const actionIndex = findParentActionIndex(nodeId);
    if (actionIndex !== null) {
        const actionSequence = treeData.actions || [];
        return actionSequence[actionIndex] || null;
    }
    return null;
}

// Find all leaf nodes (nodes with no children) in a subtree
function findLeafNodes(nodeId) {
    const nodes = treeData.nodes || {};
    const node = nodes[nodeId];
    if (!node) return [];

    const children = node.children_ids || [];
    if (children.length === 0) {
        return [nodeId];
    }

    const leaves = [];
    for (const childId of children) {
        leaves.push(...findLeafNodes(childId));
    }
    return leaves;
}

// Find "action boundary" nodes - the last nodes before the next action starts
// These are nodes that either have no children OR whose children are all action nodes
function findActionBoundaryNodes(actionNodeId) {
    // When an action is collapsed, find the next visible nodes to show
    // Skip intermediate (solver/time/constraint) nodes and return next action nodes or leaves
    const nodes = treeData.nodes || {};
    const actionNode = nodes[actionNodeId];
    if (!actionNode) return [];

    const boundaryNodes = [];
    const visited = new Set();

    function traverse(nodeId) {
        if (visited.has(nodeId)) return;
        visited.add(nodeId);

        const node = nodes[nodeId];
        if (!node) return;

        // If this is an ACTION node (not the starting one), it's a boundary
        if (node.node_type === 'action') {
            boundaryNodes.push(nodeId);
            return;
        }

        const children = node.children_ids || [];

        // If no children, this is a leaf intermediate node - include it
        if (children.length === 0) {
            boundaryNodes.push(nodeId);
            return;
        }

        // Continue traversing through intermediate nodes
        for (const childId of children) {
            traverse(childId);
        }
    }

    // Start from the action node's children (skip the action node itself)
    const children = actionNode.children_ids || [];
    for (const childId of children) {
        traverse(childId);
    }

    return boundaryNodes;
}

// Check if an action has intermediate children (solver/time/constraint nodes)
function hasIntermediateChildren(actionNodeId) {
    const nodes = treeData.nodes || {};
    const actionNode = nodes[actionNodeId];
    if (!actionNode) return false;

    const children = actionNode.children_ids || [];
    for (const childId of children) {
        const child = nodes[childId];
        if (child && isIntermediateNode(child)) {
            return true;
        }
    }
    return false;
}

// Check if a node should be visible
function isNodeVisible(node, nodeId) {
    // Root is always visible
    if (node.node_type === 'root') {
        return true;
    }

    // Action nodes visibility rules
    if (node.node_type === 'action') {
        const status = node.action_status || 'ok';

        // FAILED action nodes are ALWAYS visible - they are terminal (red nodes)
        if (status !== 'ok') {
            return true;
        }

        // Successful action nodes: hide when collapsed, show when expanded
        const actionIndex = actionNodeToIndex[nodeId];
        if (actionIndex !== null && actionIndex !== undefined && collapsedActionIndices.has(actionIndex)) {
            return false;
        }
        return true;
    }

    // For intermediate nodes (solver/time/constraint)
    if (isIntermediateNode(node)) {
        const children = node.children_ids || [];

        // LEAF intermediate nodes (no children) are ALWAYS visible
        // These are the final outputs of an action chain
        if (children.length === 0) {
            return true;
        }

        // Check if all children are action nodes (this node is the last before next action)
        const nodes = treeData.nodes || {};
        const allChildrenAreActions = children.every(childId => {
            const child = nodes[childId];
            return child && child.node_type === 'action';
        });

        // If all children are actions, this is a "boundary" solver - ALWAYS show it
        // When collapsed: this is the visible result (purple)
        // When expanded: still visible as part of the chain
        if (allChildrenAreActions) {
            return true;
        }

        // Otherwise, hide if parent action is collapsed
        const parentActionIndex = findParentActionIndex(nodeId);
        if (parentActionIndex !== null && collapsedActionIndices.has(parentActionIndex)) {
            return false;
        }
    }

    return true;
}

// Get visible children of a node (skips hidden nodes)
function getVisibleChildren(nodeId) {
    const nodes = treeData.nodes || {};
    const node = nodes[nodeId];
    if (!node) return [];

    const directChildren = node.children_ids || [];

    // Return visible children, recursively skipping hidden nodes
    const result = [];
    for (const childId of directChildren) {
        const childNode = nodes[childId];
        if (!childNode) continue;

        if (isNodeVisible(childNode, childId)) {
            result.push(childId);
        } else {
            // Child is hidden, get its visible children recursively
            result.push(...getVisibleChildren(childId));
        }
    }
    return result;
}

// Get all visible node IDs
function getVisibleNodeIds() {
    const nodes = treeData.nodes || {};
    const visibleIds = [];
    for (const [id, node] of Object.entries(nodes)) {
        if (isNodeVisible(node, id)) {
            visibleIds.push(id);
        }
    }
    return visibleIds;
}

// Calculate tree layout using a simple level-based algorithm
// This is more robust for DAG structures and prevents overlapping
function calculateLayout() {
    const nodes = treeData.nodes || {};
    const rootId = treeData.root_id;
    const layout = {};

    // Build adjacency list using visible children
    const children = {};
    for (const [id, node] of Object.entries(nodes)) {
        if (isNodeVisible(node, id)) {
            children[id] = getVisibleChildren(id);
        }
    }

    // Calculate depth (level) for each visible node using BFS
    // This handles DAGs correctly by taking the minimum depth
    const depths = {};
    const visited = new Set();
    const queue = [[rootId, 0]];

    while (queue.length > 0) {
        const [nodeId, depth] = queue.shift();
        const node = nodes[nodeId];
        if (!node || !isNodeVisible(node, nodeId)) continue;
        if (visited.has(nodeId)) continue;

        visited.add(nodeId);
        depths[nodeId] = depth;

        for (const childId of children[nodeId] || []) {
            if (!visited.has(childId)) {
                queue.push([childId, depth + 1]);
            }
        }
    }

    // Group nodes by their level
    const levels = {};
    let maxLevel = 0;
    for (const [nodeId, depth] of Object.entries(depths)) {
        if (!levels[depth]) levels[depth] = [];
        levels[depth].push(nodeId);
        maxLevel = Math.max(maxLevel, depth);
    }

    // Position nodes within each level
    // Use a simple even distribution with minimum spacing
    let maxWidth = 0;
    const MIN_NODE_SPACING = NODE_SPACING + 10;  // Minimum space between node centers

    for (let level = 0; level <= maxLevel; level++) {
        const nodesAtLevel = levels[level] || [];
        const count = nodesAtLevel.length;

        if (count === 0) continue;

        // Calculate total width needed for this level
        const levelWidth = (count - 1) * MIN_NODE_SPACING;
        const startX = -levelWidth / 2;

        // Sort nodes to minimize edge crossings
        // Try to place children near their parents
        if (level > 0) {
            nodesAtLevel.sort((a, b) => {
                const nodeA = nodes[a];
                const nodeB = nodes[b];
                const parentA = (nodeA.parent_ids || [])[0];
                const parentB = (nodeB.parent_ids || [])[0];
                const posA = parentA && layout[parentA] ? layout[parentA].x : 0;
                const posB = parentB && layout[parentB] ? layout[parentB].x : 0;
                return posA - posB;
            });
        }

        // Assign x positions
        nodesAtLevel.forEach((nodeId, idx) => {
            const x = startX + idx * MIN_NODE_SPACING;
            layout[nodeId] = {
                x: x,
                y: level * LEVEL_HEIGHT + NODE_RADIUS + 40,
                level: level
            };
            maxWidth = Math.max(maxWidth, Math.abs(x));
        });
    }

    // Second pass: try to center parents over their children
    for (let level = maxLevel - 1; level >= 0; level--) {
        const nodesAtLevel = levels[level] || [];

        for (const nodeId of nodesAtLevel) {
            const childIds = children[nodeId] || [];
            if (childIds.length === 0) continue;

            // Calculate average position of children
            let sumX = 0;
            let count = 0;
            for (const childId of childIds) {
                if (layout[childId]) {
                    sumX += layout[childId].x;
                    count++;
                }
            }

            if (count > 0) {
                const targetX = sumX / count;
                // Only move if it doesn't cause overlap with siblings
                const siblings = levels[level];
                const myIdx = siblings.indexOf(nodeId);
                const leftNeighbor = myIdx > 0 ? layout[siblings[myIdx - 1]] : null;
                const rightNeighbor = myIdx < siblings.length - 1 ? layout[siblings[myIdx + 1]] : null;

                let newX = targetX;
                if (leftNeighbor && newX < leftNeighbor.x + MIN_NODE_SPACING) {
                    newX = leftNeighbor.x + MIN_NODE_SPACING;
                }
                if (rightNeighbor && newX > rightNeighbor.x - MIN_NODE_SPACING) {
                    newX = rightNeighbor.x - MIN_NODE_SPACING;
                }

                layout[nodeId].x = newX;
                maxWidth = Math.max(maxWidth, Math.abs(newX));
            }
        }
    }

    return { layout, maxWidth, maxLevel };
}

function renderGraph() {
    const svg = document.getElementById('graph');
    const { layout, maxWidth, maxLevel } = calculateLayout();

    // Set SVG size
    const width = Math.max(800, maxWidth * 2 + 200);
    const height = (maxLevel + 1) * LEVEL_HEIGHT + 100;
    svg.setAttribute('viewBox', `${-width/2} 0 ${width} ${height}`);
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

    const nodes = treeData.nodes || {};
    const leftX = -width / 2 + 60;
    const actionSequence = treeData.actions || [];

    // Draw edges first (so they're behind nodes)
    for (const [nodeId, node] of Object.entries(nodes)) {
        if (!isNodeVisible(node, nodeId)) continue;

        const pos = layout[nodeId];
        if (!pos) continue;

        const visibleKids = getVisibleChildren(nodeId);

        for (const childId of visibleKids) {
            const childNode = nodes[childId];
            if (!childNode) continue;

            const childPos = layout[childId];
            if (!childPos) continue;

            const midY = (pos.y + childPos.y) / 2;
            const pathD = `M${pos.x},${pos.y + NODE_RADIUS} ` +
                          `Q${pos.x},${midY} ${childPos.x},${childPos.y - NODE_RADIUS}`;

            const edgeClass = (childNode.pruned || node.pruned) ? 'edge pruned-edge' : 'edge';
            html += `<path class="${edgeClass}" d="${pathD}" />`;
        }
    }

    // ============================================
    // BUILD LABEL LIST FROM ACTION SEQUENCE (BY INSTANCE INDEX)
    // ============================================

    // For each action INSTANCE, find the minimum Y position of nodes belonging to it
    // (either action node itself if expanded, or boundary nodes if collapsed)
    const actionInstanceYPositions = {};  // Map from instance index to { minY, maxY }

    for (let instanceIdx = 0; instanceIdx < actionSequence.length; instanceIdx++) {
        let minY = Infinity;
        let maxY = -Infinity;

        // Find all visible nodes that belong to this action instance
        for (const [nodeId, pos] of Object.entries(layout)) {
            const node = nodes[nodeId];
            if (!node) continue;

            // Check if this node belongs to this action instance
            const parentActionIdx = findParentActionIndex(nodeId);
            if (parentActionIdx === instanceIdx) {
                minY = Math.min(minY, pos.y);
                maxY = Math.max(maxY, pos.y);
            }

            // Also check if this IS the action node for this instance
            if (node.node_type === 'action' && actionNodeToIndex[nodeId] === instanceIdx) {
                minY = Math.min(minY, pos.y);
                maxY = Math.max(maxY, pos.y);
            }
        }

        if (minY !== Infinity) {
            actionInstanceYPositions[instanceIdx] = { minY, maxY };
        }
    }

    // Build labels array with proper Y ordering based on action sequence
    const labelsToRender = [];
    let prevMaxY = layout[treeData.root_id]?.y || 0;  // Start after root

    for (let instanceIdx = 0; instanceIdx < actionSequence.length; instanceIdx++) {
        const actionName = actionSequence[instanceIdx];
        const positions = actionInstanceYPositions[instanceIdx];

        if (!positions) continue;

        // Label Y = midpoint between previous action's end and this action's start
        const labelY = (prevMaxY + positions.minY) / 2;

        labelsToRender.push({
            type: 'action',
            name: actionName,
            instanceIndex: instanceIdx,  // Track instance for click handling
            y: labelY,
            isCollapsed: collapsedActionIndices.has(instanceIdx),
            hasFailure: false  // Will check below
        });

        // Check for failures in this action instance's nodes
        const instanceNodes = actionIndexToNodes[instanceIdx] || [];
        for (const nodeId of instanceNodes) {
            const node = nodes[nodeId];
            if (node && node.action_status !== 'ok') {
                labelsToRender[labelsToRender.length - 1].hasFailure = true;
                break;
            }
        }

        prevMaxY = positions.maxY;
    }

    // Now add Solver/Time labels for intermediate nodes
    // ONLY show these labels when the parent action is EXPANDED
    const actionLabelYs = new Set(labelsToRender.map(l => Math.round(l.y)));
    const solverTimeLabels = [];

    for (const [nodeId, node] of Object.entries(nodes)) {
        if (!isNodeVisible(node, nodeId)) continue;
        const pos = layout[nodeId];
        if (!pos) continue;

        const nodeType = node.node_type || 'action';
        if (nodeType !== 'solver' && nodeType !== 'time' && nodeType !== 'constraint') continue;

        // CRITICAL: Only show solver/time labels when parent action is EXPANDED
        // If the parent action is collapsed, the intermediate nodes are hidden
        // and showing a label would be confusing ("out of nowhere")
        const parentActionIndex = findParentActionIndex(nodeId);
        if (parentActionIndex !== null && collapsedActionIndices.has(parentActionIndex)) {
            continue;  // Skip label for collapsed action's intermediate nodes
        }

        // Find the previous visible node to calculate label Y
        const parentIds = node.parent_ids || [];
        let parentY = pos.y - LEVEL_HEIGHT;
        for (const pid of parentIds) {
            if (layout[pid]) {
                parentY = layout[pid].y;
                break;
            }
        }

        const labelY = (parentY + pos.y) / 2;
        const roundedY = Math.round(labelY);

        // Skip if too close to an action label
        let tooClose = false;
        for (const aY of actionLabelYs) {
            if (Math.abs(roundedY - aY) < 30) {
                tooClose = true;
                break;
            }
        }
        if (tooClose) continue;

        // Check if we already have a label at this Y position
        const existingLabel = solverTimeLabels.find(l => Math.abs(Math.round(l.y) - roundedY) < 30);
        if (!existingLabel) {
            solverTimeLabels.push({
                type: nodeType === 'solver' ? 'solver' : 'time',
                y: labelY
            });
        }
    }

    // Merge solver/time labels into main list
    labelsToRender.push(...solverTimeLabels);

    // Sort by Y position
    labelsToRender.sort((a, b) => a.y - b.y);

    // Final collision avoidance pass
    const MIN_LABEL_SPACING = 28;
    const usedYPositions = [];

    for (const label of labelsToRender) {
        let y = label.y;

        for (const usedY of usedYPositions) {
            if (Math.abs(y - usedY) < MIN_LABEL_SPACING) {
                y = usedY + MIN_LABEL_SPACING;
            }
        }

        label.y = y;
        usedYPositions.push(y);
    }

    // Render all labels
    for (const label of labelsToRender) {
        if (label.type === 'action') {
            const isSelected = selectedActionName === label.name;
            let labelClass = 'level-action';
            if (label.hasFailure) labelClass += ' has-failure';
            if (isSelected) labelClass += ' selected';

            const toggleIcon = label.isCollapsed ? '+' : '−';
            const toggleColor = label.isCollapsed ? 'var(--accent-gold)' : 'var(--text-dim)';
            const toggleX = leftX - 25;

            html += `
                <g transform="translate(${toggleX}, ${label.y})"
                   onclick="event.stopPropagation(); toggleActionCollapse(${label.instanceIndex})"
                   style="cursor: pointer;">
                    <circle r="10" fill="var(--bg-card)" stroke="${toggleColor}" stroke-width="1.5" />
                    <text y="4" fill="${toggleColor}" font-size="14" font-weight="bold"
                          text-anchor="middle">${toggleIcon}</text>
                </g>
            `;

            html += `<text class="${labelClass}" x="${leftX}" y="${label.y}" ` +
                `text-anchor="start" onclick="toggleActionPanel('${label.name}')" ` +
                `style="cursor: pointer;">${label.name}</text>`;

        } else if (label.type === 'solver') {
            const labelClass = selectedLabelType === 'solver' ? 'level-action selected' : 'level-action';
            html += `<text class="${labelClass}" x="${leftX}" y="${label.y}" ` +
                `text-anchor="start" onclick="showLabelPanel('solver')" ` +
                `style="cursor: pointer; fill: var(--accent-purple);">Solver</text>`;

        } else if (label.type === 'time') {
            const labelClass = selectedLabelType === 'time' ? 'level-action selected' : 'level-action';
            html += `<text class="${labelClass}" x="${leftX}" y="${label.y}" ` +
                `text-anchor="start" onclick="showLabelPanel('time')" ` +
                `style="cursor: pointer; fill: var(--accent-cyan);">Time</text>`;
        }
    }

    // Draw nodes (only visible ones)
    for (const [nodeId, node] of Object.entries(nodes)) {
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
        if (isPruned) {
            statusClass = 'pruned';
        } else if (isRoot) {
            statusClass = 'root';
        } else if (nodeType === 'solver') {
            statusClass = 'solver';
        } else if (nodeType === 'time') {
            statusClass = 'time';
        } else if (nodeType === 'constraint') {
            statusClass = 'constraint';
        } else if (status !== 'ok') {
            statusClass = 'failed';
        } else {
            statusClass = 'success';
        }

        const classes = `node ${statusClass} ${isSelected ? 'selected' : ''}`;
        html += `
            <g class="${classes.trim()}"
               data-node-id="${nodeId}"
               transform="translate(${pos.x}, ${pos.y})"
               onclick="selectNode('${nodeId}')"
               onmouseenter="showTooltip(event, '${nodeId}')"
               onmouseleave="hideTooltip()">
                <circle class="node-circle" r="${NODE_RADIUS}" cx="0" cy="0" />
                <text class="node-label" y="4">${nodeId.replace('state', 'S')}</text>
            </g>
        `;
    }

    svg.innerHTML = html;
}

function selectNode(nodeId) {
    selectedNodeId = nodeId;
    renderGraph();
    renderDetail(nodeId);
}

// =====================================================================
// Action Panel Functions
// =====================================================================

function toggleActionPanel(actionName) {
    if (selectedActionName === actionName) {
        hideActionPanel();
    } else {
        showActionPanel(actionName);
    }
}

function showActionPanel(actionName) {
    selectedActionName = actionName;
    selectedLabelType = null;  // Clear label selection
    const panel = document.getElementById('action-panel');
    const title = document.getElementById('action-panel-title');
    const content = document.getElementById('action-panel-content');

    title.textContent = `Action: ${actionName}`;

    // Get action definition from treeData
    const actionDef = treeData.action_definitions?.[actionName];
    content.innerHTML = renderActionDefinition(actionDef);

    panel.classList.add('visible');
    renderGraph();  // Re-render to update selected state
}

function hideActionPanel() {
    selectedActionName = null;
    selectedLabelType = null;
    const panel = document.getElementById('action-panel');
    panel.classList.remove('visible');
    renderGraph();  // Re-render to update selected state
}

// Show Solver or Time panel
function showLabelPanel(labelType) {
    if (selectedLabelType === labelType) {
        hideActionPanel();
        return;
    }

    selectedLabelType = labelType;
    selectedActionName = null;  // Clear action selection
    const panel = document.getElementById('action-panel');
    const title = document.getElementById('action-panel-title');
    const content = document.getElementById('action-panel-content');

    if (labelType === 'solver') {
        title.textContent = 'Solver Rules';
        const rules = treeData.solver_definitions?.solver?.rules;
        content.innerHTML = rules ? renderSolverRules(rules) :
            '<p style="color: var(--text-dim);">No solver rules defined</p>';
    } else if (labelType === 'time') {
        title.textContent = 'Time Constraints';
        const branches = treeData.constraint_definitions?.constraint?.branches;
        content.innerHTML = branches ? renderConstraintBranches(branches) :
            '<p style="color: var(--text-dim);">No time constraints defined</p>';
    }

    panel.classList.add('visible');
    renderGraph();  // Re-render to update selected state
}

function renderActionDefinition(def) {
    if (!def) {
        return '<p style="color: var(--text-dim);">No definition available</p>';
    }

    let html = '';

    // Preconditions
    if (def.preconditions && def.preconditions.length > 0) {
        html += `
            <div class="condition-section">
                <div class="condition-section-title precondition">Preconditions</div>
                <div class="condition-tree">
                    ${renderPreconditions(def.preconditions)}
                </div>
            </div>
        `;
    }

    // Effects
    if (def.effects && def.effects.length > 0) {
        html += `
            <div class="condition-section">
                <div class="condition-section-title effects">Effects</div>
                <div class="condition-tree">
                    ${renderEffects(def.effects)}
                </div>
            </div>
        `;
    }

    if (!html) {
        html = '<p style="color: var(--text-dim);">No preconditions or effects defined</p>';
    }

    return html;
}

function renderPreconditions(preconditions) {
    return preconditions.map(cond => renderCondition(cond, 'precondition')).join('');
}

function renderCondition(cond, context) {
    if (cond.type === 'or') {
        const subConds = (cond.conditions || []).map((c, i) => {
            const prefix = i === 0 ? '' : '<span class="condition-keyword or">OR</span>';
            return `${prefix}${renderCondition(c, context)}`;
        }).join('');
        return `<div class="condition-block or">${subConds}</div>`;
    } else if (cond.type === 'and') {
        const subConds = (cond.conditions || []).map((c, i) => {
            const prefix = i === 0 ? '' : '<span class="condition-keyword and">AND</span>';
            return `${prefix}${renderCondition(c, context)}`;
        }).join('');
        return `<div class="condition-block and">${subConds}</div>`;
    } else if (cond.type === 'attribute_check') {
        return renderAttributeCheck(cond);
    } else {
        return `<span class="condition-expr">${cond.description || 'Unknown condition'}</span>`;
    }
}

function renderAttributeCheck(cond) {
    const attr = cond.attribute || '';
    const op = getOperatorSymbol(cond.operator);
    let val = cond.value;
    if (Array.isArray(val)) {
        val = '{' + val.join(', ') + '}';
    }
    return `
        <span class="condition-expr">
            <span class="attr">${attr}</span>
            <span class="op">${op}</span>
            <span class="val">${val}</span>
        </span>
    `;
}

function renderEffects(effects) {
    let html = '';
    for (const effect of effects) {
        if (effect.type === 'conditional') {
            html += renderConditionalEffect(effect);
        } else if (effect.type === 'set_attribute') {
            html += renderSetAttributeEffect(effect);
        } else if (effect.type === 'trend') {
            html += renderTrendEffect(effect);
        } else {
            html += `<div class="condition-block">${effect.description || 'Unknown effect'}</div>`;
        }
    }
    return html;
}

function renderConditionalEffect(effect) {
    const branchType = effect.branch_type || 'if';
    const keyword = branchType.toUpperCase();
    const keywordClass = branchType.toLowerCase();

    let conditionHtml = '';
    if (effect.condition) {
        conditionHtml = renderCondition(effect.condition, 'effect');
    }

    let thenHtml = '';
    if (effect.then_effects && effect.then_effects.length > 0) {
        thenHtml = effect.then_effects.map(e => {
            if (e.type === 'set_attribute') {
                return `<div><span class="effect-target">${e.target}</span> = ` +
                       `<span class="effect-value">${e.value}</span></div>`;
            } else if (e.type === 'trend') {
                return `<div><span class="effect-target">${e.target}</span>.trend = ` +
                       `<span class="effect-value">${e.direction}</span></div>`;
            }
            return `<div>${e.description || 'effect'}</div>`;
        }).join('');
    }

    let elseHtml = '';
    if (effect.else_effects && effect.else_effects.length > 0) {
        // Check if else contains a conditional (ELIF) or just direct effects (ELSE)
        const hasConditional = effect.else_effects.some(e => e.type === 'conditional');
        if (hasConditional) {
            // Render nested conditionals (ELIF chain)
            elseHtml = effect.else_effects.map(e => {
                if (e.type === 'conditional') {
                    return renderConditionalEffect(e);
                } else if (e.type === 'set_attribute') {
                    return `<div class="condition-block else">
                        <span class="condition-keyword else">ELSE</span>
                        <div class="nested-conditions">
                            <div><span class="effect-target">${e.target}</span> =
                            <span class="effect-value">${e.value}</span></div>
                        </div>
                    </div>`;
                } else if (e.type === 'trend') {
                    return `<div class="condition-block else">
                        <span class="condition-keyword else">ELSE</span>
                        <div class="nested-conditions">
                            <div><span class="effect-target">${e.target}</span>.trend =
                            <span class="effect-value">${e.direction}</span></div>
                        </div>
                    </div>`;
                }
                return '';
            }).join('');
        } else {
            // Pure ELSE block with direct effects
            const elseContent = effect.else_effects.map(e => {
                if (e.type === 'set_attribute') {
                    return `<div><span class="effect-target">${e.target}</span> = ` +
                           `<span class="effect-value">${e.value}</span></div>`;
                } else if (e.type === 'trend') {
                    return `<div><span class="effect-target">${e.target}</span>.trend = ` +
                           `<span class="effect-value">${e.direction}</span></div>`;
                }
                return `<div>${e.description || 'effect'}</div>`;
            }).join('');
            elseHtml = `
                <div class="condition-block else">
                    <span class="condition-keyword else">ELSE</span>
                    <div class="nested-conditions">${elseContent}</div>
                </div>
            `;
        }
    }

    return `
        <div class="condition-block ${keywordClass}">
            <span class="condition-keyword ${keywordClass}">${keyword}</span>
            ${conditionHtml}
            <div class="nested-conditions">${thenHtml}</div>
        </div>
        ${elseHtml}
    `;
}

function renderSetAttributeEffect(effect) {
    return `
        <div class="condition-block">
            <span class="effect-target">${effect.target}</span> =
            <span class="effect-value">${effect.value}</span>
        </div>
    `;
}

function renderTrendEffect(effect) {
    return `
        <div class="condition-block">
            <span class="effect-target">${effect.target}</span>.trend =
            <span class="effect-value">${effect.direction}</span>
        </div>
    `;
}

function renderDetail(nodeId) {
    const panel = document.getElementById('detail-panel');
    const node = treeData.nodes[nodeId];

    if (!node) {
        panel.className = 'detail-panel empty';
        panel.innerHTML = `<div class="empty-icon">◉</div><p>Node not found</p>`;
        return;
    }

    panel.className = 'detail-panel';

    const snapshot = node.snapshot?.object_state || {};
    // Filter out debug/internal changes like [CONDITIONAL_EVAL]
    const changes = (node.changes || []).filter(c => {
        const attr = c.attribute || '';
        return !attr.startsWith('[') && !attr.endsWith(']');
    });
    const changedAttrs = new Set(changes.map(c => {
        let attr = c.attribute || '';
        if (attr.endsWith('.trend')) attr = attr.slice(0, -6);
        return attr;
    }));

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
    if (isPruned) {
        nodeTypeLabel = 'Pruned';
        nodeTypeColor = '#484f58';
    } else if (nodeType === 'root') {
        nodeTypeLabel = 'Initial State';
        nodeTypeColor = 'var(--accent-gold)';
    } else if (nodeType === 'solver') {
        nodeTypeLabel = 'Solver';
        nodeTypeColor = 'var(--accent-purple)';
    } else if (nodeType === 'time') {
        nodeTypeLabel = 'Time';
        nodeTypeColor = 'var(--accent-cyan)';
    } else if (nodeType === 'constraint') {
        nodeTypeLabel = 'Constraint';
        nodeTypeColor = 'var(--accent-cyan)';
    }

    let html = `
        <div class="detail-header">
            <h2>${nodeId}</h2>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span style="background: ${nodeTypeColor}; color: #0d1117; padding: 2px 8px;
                             border-radius: 4px; font-size: 0.75em; font-weight: 600;">
                    ${nodeTypeLabel}
                </span>
                <div class="action ${statusClass}">${node.action_name || 'Initial State'}</div>
            </div>
    `;

    if (node.branch_condition) {
        const bc = node.branch_condition;
        html += `<div class="branch">${formatBranchCondition(bc)}</div>`;
    }

    if (node.pruned) {
        html += `<div style="color: #484f58; margin-top: 8px; font-size: 0.9em;">` +
                `Pruned: ${node.pruned_reason || 'User resolved uncertainty'}</div>`;
    }

    if (node.action_error) {
        html += `<div style="color: var(--accent-red); margin-top: 8px; ` +
                `font-size: 0.9em;">${node.action_error}</div>`;
    }

    // Show merged node info
    if (isMerged) {
        html += `<div style="color: var(--text-dim); margin-top: 8px; ` +
                `font-size: 0.9em;">Merged node (${parentIds.length} parents)</div>`;
    }

    html += '</div>';

    // SECTION 1: World State (first, collapsed by default)
    html += `
        <div class="section collapsed">
            <div class="section-title" onclick="toggleSection(this)">World State</div>
            <div class="section-content">
            <div class="attr-list" id="attr-list">
    `;

    const parts = snapshot.parts || {};
    const globalAttrs = snapshot.global_attributes || {};

    const relevantAttrs = [];
    const otherAttrs = [];

    // Helper to check if an attribute is "relevant" (should be highlighted)
    // Relevant = attribute has changes, OR it's the root node (show all)
    const isAttrRelevant = (path) => {
        if (changedAttrs.size > 0) {
            return changedAttrs.has(path);
        }
        // For root node (no action), show all as relevant
        return isRoot;
    };

    // Process parts
    for (const [partName, partData] of Object.entries(parts)) {
        const attrs = partData.attributes || {};
        for (const [attrName, attrData] of Object.entries(attrs)) {
            const fullPath = `${partName}.${attrName}`;
            const isRelevant = isAttrRelevant(fullPath);
            const entry = { path: fullPath, data: attrData, isChanged: isRelevant };

            if (isRelevant) {
                relevantAttrs.push(entry);
            } else {
                otherAttrs.push(entry);
            }
        }
    }

    // Process global attributes
    for (const [attrName, attrData] of Object.entries(globalAttrs)) {
        const isRelevant = isAttrRelevant(attrName);
        const entry = { path: attrName, data: attrData, isChanged: isRelevant };

        if (isRelevant) {
            relevantAttrs.push(entry);
        } else {
            otherAttrs.push(entry);
        }
    }

    // Render relevant attributes
    for (const { path, data, isChanged } of relevantAttrs) {
        html += renderAttrItem(path, data, isChanged, true);
    }

    html += '</div>';  // close attr-list

    // Other attributes (expandable)
    if (otherAttrs.length > 0) {
        html += `
            <div class="expand-btn" onclick="toggleOthers()">
                Show ${otherAttrs.length} other attributes ▼
            </div>
            <div class="attr-list hidden" id="other-attrs">
        `;

        for (const { path, data } of otherAttrs) {
            html += renderAttrItem(path, data, false, false);
        }

        html += '</div>';
    }

    html += '</div></div>';  // close section-content and section (World State)

    // SECTION 2+: Changes sections (collapsed by default)
    if (isMerged) {
        // Primary parent changes (first parent)
        const primaryParent = parentIds[0];
        const pLabel = primaryParent.replace('state', 'S');
        html += `
            <div class="section collapsed">
                <div class="section-title" onclick="toggleSection(this)">` +
                `Changes from ${pLabel}</div>
                <div class="section-content">
                    <div class="change-list">
        `;
        if (changes.length > 0) {
            for (const change of changes) {
                html += `
                    <div class="change-item">
                        <span class="attr-name">${change.attribute}</span>
                        <span class="change-before">${formatValue(change.before) || '—'}</span>
                        <span class="change-arrow">→</span>
                        <span class="change-after">${formatValue(change.after) || '—'}</span>
                    </div>
                `;
            }
        } else {
            html += `<div class="change-item" style="color: var(--text-dim);">No changes (same state)</div>`;
        }
        html += '</div></div></div>';

        // Additional parent changes from incoming_edges
        if (node.incoming_edges && node.incoming_edges.length > 0) {
            for (const edge of node.incoming_edges) {
                const edgeChanges = (edge.changes || []).filter(c => {
                    const attr = c.attribute || '';
                    return !attr.startsWith('[') && !attr.endsWith(']');
                });
                if (edgeChanges.length > 0) {
                    const eLabel = edge.parent_id.replace('state', 'S');
                    html += `
                        <div class="section collapsed">
                            <div class="section-title" onclick="toggleSection(this)">` +
                            `Changes from ${eLabel}</div>
                            <div class="section-content">
                                <div class="change-list">
                    `;
                    for (const change of edgeChanges) {
                        html += `
                            <div class="change-item">
                                <span class="attr-name">${change.attribute}</span>
                                <span class="change-before">${formatValue(change.before) || '—'}</span>
                                <span class="change-arrow">→</span>
                                <span class="change-after">${formatValue(change.after) || '—'}</span>
                            </div>
                        `;
                    }
                    html += '</div></div></div>';
                }
            }
        }
    } else if (changes.length > 0) {
        html += `
            <div class="section collapsed">
                <div class="section-title" onclick="toggleSection(this)">Changes</div>
                <div class="section-content">
                    <div class="change-list">
        `;

        for (const change of changes) {
            html += `
                <div class="change-item">
                    <span class="attr-name">${change.attribute}</span>
                    <span class="change-before">${formatValue(change.before) || '—'}</span>
                    <span class="change-arrow">→</span>
                    <span class="change-after">${formatValue(change.after) || '—'}</span>
                </div>
            `;
        }

        html += '</div></div></div>';
    }

    panel.innerHTML = html;

    // Restore section states if we have saved states for this node
    if (sectionStates[nodeId]) {
        const sections = document.querySelectorAll('.section');
        const states = sectionStates[nodeId];
        sections.forEach((s, i) => {
            if (i < states.length) {
                if (states[i]) {
                    s.classList.add('collapsed');
                } else {
                    s.classList.remove('collapsed');
                }
            }
        });
    }

    // Restore "other attributes" expanded state
    if (otherAttrsStates[nodeId]) {
        const el = document.getElementById('other-attrs');
        const btn = document.querySelector('.expand-btn');
        if (el && btn) {
            el.classList.remove('hidden');
            btn.textContent = btn.textContent.replace('▼', '▲');
        }
    }
}

function toggleSection(titleEl) {
    const section = titleEl.parentElement;
    section.classList.toggle('collapsed');
    // Save section state for current node
    if (selectedNodeId) {
        const sections = document.querySelectorAll('.section');
        const states = [];
        sections.forEach(s => states.push(s.classList.contains('collapsed')));
        sectionStates[selectedNodeId] = states;
    }
}

function formatValue(value) {
    // Handle value sets (arrays)
    if (Array.isArray(value)) {
        return '{' + value.join(', ') + '}';
    }
    return value || '—';
}

function getOperatorSymbol(op) {
    switch(op) {
        case 'equals': return '==';
        case 'not_equals': return '!=';
        case 'in': return '∈';
        case 'not_in': return '∉';
        case 'gt': return '>';
        case 'gte': return '>=';
        case 'lt': return '<';
        case 'lte': return '<=';
        default: return op || '==';
    }
}

// Render solver rules for the detail panel
function renderSolverRules(rules) {
    if (!rules || rules.length === 0) return '<p style="color: var(--text-dim);">No rules defined</p>';

    let html = '<div class="solver-rules">';
    for (const rule of rules) {
        html += `
            <div style="margin-bottom: 12px; padding: 10px; background: rgba(163, 113, 247, 0.1);
                        border-left: 3px solid var(--accent-purple); border-radius: 4px;">
                <div style="font-weight: 600; color: var(--accent-purple);">${rule.name}</div>
                <div style="font-size: 0.85em; color: var(--text-dim); margin-top: 4px;">
                    ${rule.description || ''}
                </div>
        `;

        if (rule.condition) {
            html += `<div style="margin-top: 8px; font-size: 0.85em;">
                <span style="color: var(--text-dim);">IF:</span>
                <span style="color: var(--text);">${rule.condition.description || 'condition'}</span>
            </div>`;
        }

        if (rule.implies && rule.implies.length > 0) {
            html += `<div style="margin-top: 4px; font-size: 0.85em;">
                <span style="color: var(--accent-green);">THEN:</span>
            </div>`;
            for (const effect of rule.implies) {
                html += `<div style="margin-left: 16px; font-size: 0.85em;">
                    <span style="color: var(--text);">${effect.target} = ${effect.value}</span>
                </div>`;
            }
        }

        // For simple rules with condition/implies/otherwise (no cases)
        if (rule.otherwise && rule.otherwise.length > 0 && (!rule.cases || rule.cases.length === 0)) {
            html += `<div style="margin-top: 4px; font-size: 0.85em;">
                <span style="color: var(--accent-red);">ELSE:</span>
            </div>`;
            for (const effect of rule.otherwise) {
                html += `<div style="margin-left: 16px; font-size: 0.85em;">
                    <span style="color: var(--text);">${effect.target} = ${effect.value}</span>
                </div>`;
            }
        }

        // For case-based rules: show cases first, then otherwise
        if (rule.cases && rule.cases.length > 0) {
            html += '<div style="margin-top: 8px; font-size: 0.85em;">';
            for (let i = 0; i < rule.cases.length; i++) {
                const c = rule.cases[i];
                const label = i === 0 ? 'IF' : 'ELIF';
                html += `<div style="margin-top: 4px;">
                    <span style="color: var(--accent-gold);">${label}:</span>
                    <span style="color: var(--text);">${c.condition?.description || 'condition'}</span>
                </div>`;
                html += `<div style="margin-left: 16px;">
                    <span style="color: var(--accent-green);">THEN:</span>
                </div>`;
                for (const effect of c.implies || []) {
                    html += `<div style="margin-left: 32px;">
                        <span style="color: var(--text);">${effect.target} = ${effect.value}</span>
                    </div>`;
                }
            }
            // Show otherwise AFTER cases
            if (rule.otherwise && rule.otherwise.length > 0) {
                html += `<div style="margin-top: 4px;">
                    <span style="color: var(--accent-red);">ELSE:</span>
                </div>`;
                html += `<div style="margin-left: 16px;">
                    <span style="color: var(--accent-green);">THEN:</span>
                </div>`;
                for (const effect of rule.otherwise) {
                    html += `<div style="margin-left: 32px;">
                        <span style="color: var(--text);">${effect.target} = ${effect.value}</span>
                    </div>`;
                }
            }
            html += '</div>';
        }

        html += '</div>';
    }
    html += '</div>';
    return html;
}

// Render constraint branches for the detail panel
function renderConstraintBranches(branches) {
    if (!branches || branches.length === 0) return '<p style="color: var(--text-dim);">No constraints</p>';

    // Known space complements for resolving negated values
    const spaceComplements = {
        // binary_state: off, on
        'off': 'on',
        'on': 'off',
        // brightness_level: none, low, medium, high
        'none': '{low, medium, high}',
        'low': '{none, medium, high}',
        'medium': '{none, low, high}',
        'high': '{none, low, medium}',
        // battery_level: empty, low, medium, high, full
        'empty': '{low, medium, high, full}',
        'full': '{empty, low, medium, high}',
    };

    // Helper to format values - resolve negated values to actual valid values
    function formatValue(val) {
        if (typeof val === 'string' && val.startsWith('!')) {
            const excluded = val.slice(1);
            // Look up the complement in known spaces
            if (spaceComplements[excluded]) {
                return spaceComplements[excluded];
            }
            // Fallback to "not X" if unknown
            return `not ${excluded}`;
        }
        return val;
    }

    let html = '<div class="constraint-branches">';

    // Add explanation header
    html += `<p style="color: var(--text-dim); font-size: 0.85em; margin-bottom: 12px;">
        Time constraints define what states are possible when time passes and values change due to trends.
        They ensure the world stays consistent over time.
    </p>`;

    for (const branch of branches) {
        html += `
            <div style="margin-bottom: 12px; padding: 10px; background: rgba(88, 166, 255, 0.1);
                        border-left: 3px solid var(--accent-cyan); border-radius: 4px;">
        `;

        if (branch.condition) {
            html += `<div style="font-size: 0.85em;">
                <span style="color: var(--accent-gold);">IF:</span>
                <span style="color: var(--text);">${branch.condition.description || 'condition'}</span>
            </div>`;
        }

        if (branch.effects && branch.effects.length > 0) {
            html += `<div style="margin-top: 4px; margin-left: 16px; font-size: 0.85em;">
                <span style="color: var(--accent-green);">THEN:</span>
            </div>`;
            for (const effect of branch.effects) {
                html += `<div style="margin-left: 32px; font-size: 0.85em;">
                    <span style="color: var(--text);">${effect.target} = ${formatValue(effect.value)}</span>
                </div>`;
            }
        }

        // Render elif_cases
        if (branch.elif_cases && branch.elif_cases.length > 0) {
            for (const elifCase of branch.elif_cases) {
                html += `<div style="margin-top: 4px; font-size: 0.85em;">
                    <span style="color: var(--accent-gold);">ELIF:</span>
                    <span style="color: var(--text);">${elifCase.condition?.description || 'condition'}</span>
                </div>`;
                if (elifCase.effects && elifCase.effects.length > 0) {
                    html += `<div style="margin-left: 16px; font-size: 0.85em;">
                        <span style="color: var(--accent-green);">THEN:</span>
                    </div>`;
                    for (const effect of elifCase.effects) {
                        const fv = formatValue(effect.value);
                        html += `<div style="margin-left: 32px; font-size: 0.85em;">
                            <span style="color: var(--text);">${effect.target} = ${fv}</span>
                        </div>`;
                    }
                }
            }
        }

        if (branch.else_effects && branch.else_effects.length > 0) {
            html += `<div style="margin-top: 4px; font-size: 0.85em;">
                <span style="color: var(--accent-red);">ELSE:</span>
            </div>`;
            html += `<div style="margin-left: 16px; font-size: 0.85em;">
                <span style="color: var(--accent-green);">THEN:</span>
            </div>`;
            for (const effect of branch.else_effects) {
                html += `<div style="margin-left: 32px; font-size: 0.85em;">
                    <span style="color: var(--text);">${effect.target} = ${formatValue(effect.value)}</span>
                </div>`;
            }
        }

        html += '</div>';
    }
    html += '</div>';
    return html;
}

function formatBranchCondition(bc) {
    // Handle compound conditions (AND/OR)
    if (bc.compound_type && bc.sub_conditions && bc.sub_conditions.length > 0) {
        const connectorText = bc.compound_type === 'and' ? 'AND' : 'OR';
        const connector = `<span class="compound-connector">${connectorText}</span>`;
        const parts = bc.sub_conditions.map(sub => formatBranchCondition(sub));
        return parts.join(' ' + connector + ' ');
    }

    // Simple condition
    const attr = bc.attribute || '';
    let op = getOperatorSymbol(bc.operator);
    // Check if value is a set with MORE than one element
    const isMultiValueSet = Array.isArray(bc.value) && bc.value.length > 1;
    const isSingleValueArray = Array.isArray(bc.value) && bc.value.length === 1;

    // If value is a multi-value set and operator is equals/not_equals, use ∈/∉ instead
    if (isMultiValueSet) {
        if (bc.operator === 'equals' || bc.operator === 'in') {
            op = '∈';
        } else if (bc.operator === 'not_equals' || bc.operator === 'not_in') {
            op = '∉';
        }
    }

    // Determine value display
    let valueDisplay;
    if (isMultiValueSet) {
        valueDisplay = '{' + bc.value.join(', ') + '}';
    } else if (isSingleValueArray) {
        // Single-item array: unwrap and display as single value
        valueDisplay = bc.value[0] || '';
    } else {
        valueDisplay = bc.value || '';
    }

    if (!attr && !valueDisplay) {
        return bc.branch_type || '';
    }

    // Format with color classes
    const attrHtml = `<span class="attr-name">${attr}</span>`;
    const opHtml = `<span class="operator">${op}</span>`;
    const valueHtml = `<span class="value-set">${valueDisplay}</span>`;

    return `${attrHtml} ${opHtml} ${valueHtml}`;
}

function isValueSet(value) {
    return Array.isArray(value) && value.length > 1;
}

function renderAttrItem(path, data, isChanged, isRelevant) {
    const itemClass = isChanged ? 'changed' : (isRelevant ? 'relevant' : '');

    let trendHtml = '';
    if (data.trend && data.trend !== 'none') {
        const trendClass = data.trend === 'up' ? 'up' : 'down';
        const trendIcon = data.trend === 'up' ? '↑' : '↓';
        trendHtml = `<span class="trend ${trendClass}">${trendIcon} ${data.trend}</span>`;
    }

    // Add value set indicator if the value is a set
    let valueSetClass = '';
    let displayValue = formatValue(data.value);
    if (isValueSet(data.value)) {
        valueSetClass = 'value-set';
    }

    return `
        <div class="attr-item ${itemClass}">
            <span class="attr-name">${path}</span>
            <div class="attr-value">
                <span class="value ${valueSetClass}">${displayValue}</span>
                ${trendHtml}
            </div>
        </div>
    `;
}

function toggleOthers() {
    const el = document.getElementById('other-attrs');
    const btn = document.querySelector('.expand-btn');
    el.classList.toggle('hidden');

    if (el.classList.contains('hidden')) {
        btn.textContent = btn.textContent.replace('▲', '▼');
    } else {
        btn.textContent = btn.textContent.replace('▼', '▲');
    }

    // Save state for current node
    if (selectedNodeId) {
        otherAttrsStates[selectedNodeId] = !el.classList.contains('hidden');
    }
}

function showTooltip(event, nodeId) {
    const node = treeData.nodes[nodeId];
    if (!node) return;

    const tooltip = document.getElementById('tooltip');
    const parentIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);
    const isMerged = parentIds.length > 1;

    let mergedHint = '';
    if (isMerged) {
        mergedHint = `<div style="color: var(--text-dim);">Merged (${parentIds.length} parents)</div>`;
    }

    tooltip.innerHTML = `
        <div class="tooltip-title">${nodeId}</div>
        <div class="tooltip-action">${node.action_name || 'Initial State'}</div>
        ${mergedHint}
        <div class="tooltip-hint">Click to view details</div>
    `;

    const rect = event.target.getBoundingClientRect();
    const containerRect = document.querySelector('.graph-container').getBoundingClientRect();

    tooltip.style.left = (rect.right - containerRect.left + 10) + 'px';
    tooltip.style.top = (rect.top - containerRect.top) + 'px';
    tooltip.classList.add('visible');
}

function hideTooltip() {
    document.getElementById('tooltip').classList.remove('visible');
}

// Initialize: collapse all action instances by default
// When collapsed: shows solver boundary nodes (purple) instead of action nodes (green)
// Users can click action labels (+) to expand and see the action nodes
function initializeCollapsedActions() {
    const actionSequence = treeData.actions || [];
    for (let i = 0; i < actionSequence.length; i++) {
        collapsedActionIndices.add(i);
    }
}
initializeCollapsedActions();

// Initial render
renderGraph();

// Auto-select root
if (treeData.root_id) {
    selectNode(treeData.root_id);
}
"""
