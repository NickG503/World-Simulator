# World Simulator

A deterministic simulator for everyday objects with qualitative reasoning and tree-based state exploration. Define objects and actions in YAML, run simulations that branch on uncertainty, and visualize the resulting state space as an interactive graph.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## Overview

- **Knowledge-driven** – Objects, actions, and qualitative spaces defined in YAML
- **Tree/DAG execution** – Simulations produce graph structures where nodes are world states
- **Branching on uncertainty** – Unknown values trigger automatic branching
- **Value sets** – Trends create possible value ranges (e.g., `{empty, low, medium}`)
- **State deduplication** – Equivalent states merge into a DAG, reducing exponential growth
- **Interactive visualization** – HTML graphs with clickable nodes and state inspection

---

## Quick Start

```bash
# Install
uv sync

# Validate knowledge base
uv run sim validate

# Run a simulation with visualization
uv run sim simulate --obj flashlight --actions turn_on turn_off --viz

# Branching: set attribute to unknown
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on --viz
```

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              KNOWLEDGE BASE (kb/)                           │
├─────────────────┬─────────────────────────┬─────────────────────────────────┤
│   spaces/       │       objects/          │          actions/               │
│  common.yaml    │   flashlight.yaml       │   generic/ + object_specific/   │
│  (qualitative   │   (parts, attributes,   │   (preconditions, effects,      │
│   levels)       │    constraints)         │    parameters)                  │
└────────┬────────┴────────────┬────────────┴──────────────┬──────────────────┘
         │                     │                           │
         ▼                     ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REGISTRY MANAGER                                    │
│   Loads, validates, and provides access to all definitions                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TREE SIMULATION RUNNER                                 │
│                                                                             │
│  1. Create initial state (root node)                                        │
│  2. For each action:                                                        │
│     - Check for unknown attributes → Branch if needed                       │
│     - Apply action via TransitionEngine                                     │
│     - Create child node(s) with new state                                   │
│     - Deduplicate: merge nodes with identical states                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIMULATION TREE (DAG)                               │
│                                                                             │
│     state0 ──────────────────┐                                              │
│       │                      │                                              │
│       ▼                      ▼                                              │
│    state1 (success)      state2 (fail)                                      │
│       │                      │                                              │
│       ├──────────┬───────────┤  ◄── States can merge!                       │
│       ▼          ▼           ▼                                              │
│    state3     state4      state5                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VISUALIZER                                        │
│   Generates interactive HTML with graph layout and state inspection         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

```
simulator/
├── core/
│   ├── tree/                    # Tree-based simulation
│   │   ├── tree_runner.py       # Main simulation orchestrator
│   │   ├── models.py            # TreeNode, SimulationTree, WorldSnapshot
│   │   ├── node_factory.py      # Node creation and DAG merging
│   │   ├── snapshot_utils.py    # State capture and manipulation
│   │   └── constraints.py       # Constraint enforcement during branching
│   │
│   ├── engine/                  # Action execution
│   │   ├── transition_engine.py # Applies actions, checks preconditions
│   │   └── context.py           # Evaluation context for conditions/effects
│   │
│   ├── actions/                 # Action system
│   │   ├── conditions/          # Precondition types (attribute checks)
│   │   └── effects/             # Effect types (set value, set trend, conditional)
│   │
│   ├── objects/                 # Object model
│   │   ├── object_type.py       # Object definition (parts, attributes)
│   │   └── object_instance.py   # Runtime instance with current values
│   │
│   ├── attributes/              # Attribute system
│   │   ├── qualitative_space.py # Ordered value levels
│   │   └── path.py              # AttributePath helper for part.attr resolution
│   │
│   └── types.py                 # Shared TypedDicts (ChangeDict)
│
├── visualizer/
│   └── generator.py             # HTML visualization generator
│
└── cli/
    └── app.py                   # Typer CLI commands
```

---

## How Simulation Works

### 1. State Representation

Each simulation node contains a **WorldSnapshot** - an immutable capture of all attribute values:

```
WorldSnapshot
├── object_state
│   ├── type: "flashlight"
│   ├── parts
│   │   ├── battery
│   │   │   └── level: "medium" (or ["low", "medium"] for value sets)
│   │   ├── switch
│   │   │   └── position: "off"
│   │   └── bulb
│   │       ├── state: "off"
│   │       └── brightness: "none"
│   └── global_attributes: {}
└── timestamp: "2024-12-20"
```

### 2. Action Execution Flow

```
                    ┌─────────────────────┐
                    │   Receive Action    │
                    │   (e.g., turn_on)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Check Preconditions │
                    │ (e.g., battery !=   │
                    │  empty)             │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │  PASS    │    │  FAIL    │    │ UNKNOWN  │
        │(known ok)│    │(known no)│    │(branch!) │
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │               │               │
             ▼               ▼               ▼
        ┌─────────┐    ┌──────────┐    ┌──────────────┐
        │ Apply   │    │ Rejected │    │ Create 2     │
        │ Effects │    │ Node     │    │ branches:    │
        └────┬────┘    └──────────┘    │ pass + fail  │
             │                         └──────────────┘
             ▼
        ┌─────────────────────────┐
        │ Conditional Effects?    │
        │ (if battery.level == X) │
        └────────────┬────────────┘
                     │
        ┌────────────┼────────────┐
        │ Known      │ Unknown   │
        ▼            ▼            ▼
   Single node    Branch into N+1 nodes
                  (one per if/elif + else)
```

### 3. Branching on Unknown Values

When an attribute is "unknown" or has multiple possible values:

**Precondition Branching** (2 branches):
```
Parent Node (battery.level = unknown)
         │
    turn_on (requires battery != empty)
         │
    ┌────┴────┐
    ▼         ▼
SUCCESS    FAILURE
battery ∈  battery =
{low,med,  empty
high,full}
```

**Postcondition Branching** (N+1 branches):
```
Parent Node (battery.level = unknown)
         │
    turn_on (brightness depends on level)
         │
    ┌────┬────┬────┐
    ▼    ▼    ▼    ▼
  high  med  low  empty
 (full) (high)(med)(low)
```

### 4. DAG State Deduplication

When different paths lead to the same world state, nodes merge:

```
Before Merging (Tree):          After Merging (DAG):

    state0                           state0
      │                                │
   ┌──┴──┐                          ┌──┴──┐
   ▼     ▼                          ▼     ▼
state1 state2                    state1 state2
   │     │                          │     │
   ▼     ▼                          └──┬──┘
state3 state4  ◄─ identical!           ▼
   │     │                          state3 (merged)
   ▼     ▼                             │
state5 state6  ◄─ identical!           ▼
                                    state4 (merged)

Nodes: 7                          Nodes: 5 (28% reduction)
```

Each merged node tracks **incoming edges** from multiple parents, preserving the full transition history.

---

## Current Assumptions

The simulator operates under several simplifying assumptions that keep branching tractable:

### Single Unknown Per Decision Point

Each action can have at most **one unknown attribute** that determines branching:

- **Preconditions**: If an unknown attribute is checked, we get exactly 2 branches (success + failure). Multiple preconditions can exist, but only one can involve an unknown value.
  
- **Postconditions**: If conditional effects check an unknown attribute, we get N+1 branches (one per if/elif case + one else branch). All conditionals must check the **same** attribute.

This constraint prevents combinatorial explosion. With two independent unknowns in postconditions, a single action could produce dozens of branches.

### Flat Conditional Structure

Postcondition effects use a **flat if-elif-else structure** with no nested conditionals:

```yaml
# Supported: flat structure
effects:
  - type: conditional
    condition: { target: battery.level, operator: equals, value: full }
    then: [...]
  - type: conditional  
    condition: { target: battery.level, operator: equals, value: high }
    then: [...]
    else: [...]

# NOT supported: nested ifs inside then/else blocks
```

### No Clarification Questions

When facing uncertainty, the simulator **always branches** rather than asking the user for clarification. Every possible outcome is explored in parallel.

### Branch Counting

For a single action with unknowns:
- Unknown in precondition only → 2 branches (success/fail)
- Unknown in postcondition only → N+1 branches (N cases + else)
- Both unknown (same attribute) → intersection logic reduces total branches

---

## Data Models

### TreeNode

```python
TreeNode:
    id: str                      # "state0", "state1", ...
    snapshot: WorldSnapshot      # Complete world state
    parent_ids: List[str]        # Multiple parents for DAG
    children_ids: List[str]      # Child nodes
    action_name: str             # Action that led here
    action_status: str           # "ok", "rejected", "error"
    branch_condition: BranchCondition  # What condition created this branch
    changes: List[ChangeDict]    # Attribute changes from parent
    incoming_edges: List[IncomingEdge]  # Additional parent edges (DAG)
```

### BranchCondition

```python
BranchCondition:
    attribute: str               # "battery.level"
    operator: str                # "equals", "in", "not_equals"
    value: str | List[str]       # "high" or ["low", "medium"]
    source: str                  # "precondition" or "postcondition"
    branch_type: str             # "if", "elif", "else", "success", "fail"
```

### ChangeDict

```python
ChangeDict(TypedDict):
    attribute: str               # "battery.level"
    before: str | List[str]      # Previous value
    after: str | List[str]       # New value
    kind: str                    # "value", "trend", "narrowing", "constraint"
```

---

## Knowledge Base Structure

### Qualitative Spaces (`kb/spaces/`)

Define ordered value levels:

```yaml
name: battery_level
levels: [empty, low, medium, high, full]
ordered: true
```

### Objects (`kb/objects/`)

Define structure with parts and attributes:

```yaml
name: flashlight
parts:
  battery:
    level:
      space: battery_level
      default: medium
  switch:
    position:
      space: switch_position
      default: off
  bulb:
    state:
      space: on_off
      default: off
    brightness:
      space: brightness_level
      default: none

constraints:
  - type: dependency
    condition: { target: bulb.state, operator: equals, value: on }
    requires: { target: battery.level, operator: not_equals, value: empty }
```

### Actions (`kb/actions/`)

Define preconditions and effects:

```yaml
name: turn_on
preconditions:
  - type: attribute_check
    target: switch.position
    operator: equals
    value: off
  - type: attribute_check
    target: battery.level
    operator: not_equals
    value: empty

effects:
  - type: set_attribute
    target: switch.position
    value: on
  - type: set_attribute
    target: bulb.state
    value: on
  - type: conditional
    condition:
      type: attribute_check
      target: battery.level
      operator: equals
      value: high
    then:
      - type: set_attribute
        target: bulb.brightness
        value: high
  - type: set_trend
    target: battery.level
    direction: down
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `sim validate` | Validate all knowledge base files |
| `sim show object NAME` | Display object structure |
| `sim show behaviors NAME` | List available actions |
| `sim apply OBJECT ACTION` | Apply single action, show diff |
| `sim simulate --obj TYPE --actions ...` | Run simulation |
| `sim history NAME` | View simulation summary |
| `sim visualize NAME` | Generate HTML visualization |

### Simulation Options

```bash
# Basic simulation
uv run sim simulate --obj flashlight --actions turn_on turn_off

# With output name
uv run sim simulate --obj flashlight --actions turn_on --name my_test

# Set initial values
uv run sim simulate --obj flashlight --set battery.level=low --actions turn_on

# Unknown values trigger branching
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on

# Auto-open visualization
uv run sim simulate --obj flashlight --actions turn_on --viz
```

---

## Visualization

The visualizer generates interactive HTML:

- **Graph layout**: Nodes as circles, edges showing transitions
- **Click nodes**: Inspect full world state
- **Color coding**: Green (success), Red (failure), Gold (root)
- **Value sets**: Purple `{v1, v2, v3}` styling
- **Trend arrows**: ↑ (up) and ↓ (down) indicators
- **Merged nodes**: "Changes from Sx" sections for DAG nodes
- **Collapsible sections**: Expand/collapse state details

---

## Development

```bash
# Format
uv run ruff format src/

# Lint
uv run ruff check src/

# Test
uv run pytest tests/ -v

# Pre-commit
uv run pre-commit run --all-files
```

### Adding New Objects

1. Create `kb/objects/myobject.yaml`
2. Define required spaces in `kb/spaces/common.yaml`
3. Create actions in `kb/actions/object_specific/myobject/`
4. Validate: `uv run sim validate`
5. Test: `uv run sim simulate --obj myobject --actions ... --viz`

---

## Examples

See **[EXAMPLES.md](EXAMPLES.md)** for comprehensive usage examples including:

- Multi-action simulations
- Branching scenarios
- Value set exploration
- DAG merging demonstrations

---

## File Outputs

Simulations save to `outputs/histories/`:

```yaml
# example.yaml
simulation_id: example
object_type: flashlight
nodes:
  state0:
    snapshot: { ... }
    action_name: null
  state1:
    snapshot: { ... }
    action_name: turn_on
    action_status: ok
    changes:
      - attribute: switch.position
        before: off
        after: on
```

Visualizations save alongside as `*_visualization.html`.

---

## Future Ideas

Potential expansions, roughly ordered by implementation complexity:

### Multiple Unknowns in Preconditions

Currently limited to one unknown attribute per precondition check. Since preconditions are binary (pass/fail), supporting multiple unknowns is straightforward - we still produce only 2 branches, but the success branch carries constraints on multiple attributes as value sets.

### Multiple Unknowns in Postconditions

When different conditionals check different unknown attributes, branch by grouping:
- Identify which attributes each if/elif condition checks
- Create branches for each unique attribute combination
- Collect remaining possibilities into the else branch as multi-attribute value sets

This would produce nodes where multiple attributes have value sets simultaneously.

### Nested Conditional Flattening

Nested if-statements can theoretically be flattened to equivalent flat structures:

```
if A:             if A and B: X
  if B: X    →    elif A and not B: Y
  else: Y         else: Z
else: Z
```

The simulator could auto-flatten nested YAML structures during loading.

### Clarification Questions with Pruning

Instead of always branching, detect when the tree would explode and ask the user:

> "The battery level is unknown. Knowing this would reduce branches from 12 to 3. What is the battery level?"

Pruning heuristics could include branch count thresholds, depth limits, or attribute importance scoring based on how many conditions depend on it.

### State Persistence and Continuation

Load a previous simulation's final state (or any node) as the starting point for a new simulation:
- Incremental exploration ("what if I then do X from here?")
- Save/restore simulation checkpoints
- Build on existing scenarios without re-running

---

World Simulator provides a clean foundation for exploring object state spaces with deterministic, branching execution and visual exploration.
