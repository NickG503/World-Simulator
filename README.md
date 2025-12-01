# World Simulator

A deterministic simulator for everyday objects with qualitative reasoning and tree-based state exploration. YAML knowledge bases define objects, actions, and behaviors that are executed to produce simulation trees with state transitions.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## Overview

- **Knowledge driven** – Qualitative spaces, object definitions, and actions live in `kb/` and are loaded through strict schemas
- **Tree-based execution** – Simulations produce tree structures where each node represents a world state after an action
- **Branching support** – Unknown values trigger branching: preconditions split into success/fail, postconditions split by if/elif/else cases
- **Value sets** – Trends create value sets (e.g., trend down from "medium" → {empty, low, medium})
- **Visual output** – Interactive HTML visualizations show the simulation tree with clickable nodes
- **CLI oriented** – The `sim` command provides entry points for validation, inspection, simulation, and visualization

---

## Quick Start

### Installation

```bash
# Install dependencies using uv
uv sync

# Verify installation
uv run sim --help
```

### Basic Usage

```bash
# Validate the bundled knowledge base
uv run sim validate

# Inspect an object definition
uv run sim show object flashlight

# See available actions for an object
uv run sim show behaviors flashlight

# Run a simulation
uv run sim simulate --obj flashlight --actions turn_on turn_off --name demo

# View the simulation tree
uv run sim history demo

# Generate and open visualization
uv run sim visualize demo

# Branching: set attribute to unknown and watch the tree split!
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on --name branching_demo --viz
```

### Example Output

```
Simulation Complete
ID: demo
Object: flashlight
Nodes: 3
Saved: outputs/histories/demo.yaml
Successful: 2

Path: state0 -> state1 -> state2
```

---

## Project Layout

```
src/simulator/
  cli/              # Typer-based CLI commands
  core/
    actions/        # Action, Condition, Effect types & specs
    objects/        # ObjectType, ObjectInstance, AttributeTarget
    registries/     # RegistryManager + validation
    engine/         # TransitionEngine, ConditionEvaluator, EffectApplier
    tree/           # TreeSimulationRunner, SimulationTree, TreeNode
  visualizer/       # HTML visualization generator
  io/loaders/       # YAML → typed specs → runtime models
kb/
  spaces/           # Qualitative space definitions
  objects/          # Object type YAML files
  actions/          # Generic & object-specific actions
outputs/
  histories/        # Simulation tree YAML files and visualizations
```

---

## Core Concepts

### Simulation Tree

Each simulation produces a tree structure:

- **Root node (state0)**: Initial world state before any actions
- **Child nodes (state1, state2, ...)**: States after each action
- **Branching**: Unknown values cause the tree to split into multiple paths
- **Node data**: Each node contains a snapshot, action taken, changes, and status

### Branching (Phase 2)

When attributes are unknown, the simulation branches:

- **Precondition branching**: Unknown precondition attribute → 2 branches (success/fail)
- **Postcondition branching**: Unknown postcondition attribute → N+1 branches (if/elif/else cases)
- **Value sets**: Branches can have value sets like `{empty, low, medium}` representing possible values

### Preconditions

Actions have simple preconditions that check a single attribute:

```yaml
preconditions:
  - type: attribute_check
    target: battery.level
    operator: not_equals
    value: empty
```

If the precondition fails, the action is rejected and recorded as such.

### Postconditions (Effects)

Effects use flat if-elif-else structures checking a single attribute:

```yaml
effects:
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
    else:
      - type: set_attribute
        target: bulb.brightness
        value: medium
```

### Trends

Attributes can have trends (up/down) that indicate future movement:

```yaml
- type: set_trend
  target: battery.level
  direction: down
```

When branching occurs, trends create **value sets**:
- Trend "down" from "medium" → `{empty, low, medium}` (all values at or below)
- Trend "up" from "low" → `{low, medium, high, full}` (all values at or above)

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `sim validate` | Load and validate all knowledge base files |
| `sim show object NAME` | Display object structure, defaults, and constraints |
| `sim show behaviors NAME` | List behaviors available for an object |
| `sim apply OBJECT ACTION` | Apply a single action and show the diff |
| `sim simulate --obj TYPE --actions ...` | Run multi-action simulation, save tree |
| `sim history NAME` | Display simulation tree summary |
| `sim visualize NAME` | Generate interactive HTML visualization |

### Simulation Options

```bash
# Basic simulation
uv run sim simulate --obj flashlight --actions turn_on turn_off --name my_test

# With action parameters (action=value syntax)
uv run sim simulate --obj tv --actions turn_on adjust_volume=high turn_off --name tv_test

# Set initial attribute values (space-separated after --set)
uv run sim simulate --obj flashlight --set battery.level=low --actions turn_on --name low_battery

# Set multiple initial values
uv run sim simulate --obj flashlight --set battery.level=high switch.position=off --actions turn_on turn_off --name preset_test

# Set attribute to unknown (triggers branching!)
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on --name branching_demo

# Generate visualization automatically
uv run sim simulate --obj flashlight --actions turn_on turn_off --name demo --viz
```

---

## Knowledge Base

### Spaces (`kb/spaces/`)

Define qualitative levels with ordering:

```yaml
name: battery_level
levels: [empty, low, medium, high, full]
ordered: true
```

### Objects (`kb/objects/`)

Define structure, defaults, and behaviors:

```yaml
name: flashlight
parts:
  battery:
    level:
      space: battery_level
      default: medium
      mutable: true
behaviors:
  turn_on:
    preconditions: ...
    effects: ...
```

### Actions (`kb/actions/`)

Generic actions and object-specific overrides:

```yaml
name: turn_on
parameters: []
preconditions:
  - type: attribute_check
    target: switch.position
    operator: equals
    value: off
effects:
  - type: set_attribute
    target: switch.position
    value: on
```

---

## Visualization

The visualizer creates interactive HTML pages:

- **Graph view**: Nodes as circles, connected by edges
- **Click to inspect**: See full world state for any node
- **Change highlighting**: Changed attributes shown in gold
- **Value sets**: Displayed as `{v1, v2, v3}` with purple styling
- **Trend indicators**: Arrows (↑/↓) show attribute trends
- **Branch types**: Different styling for if/elif/else branches
- **Expandable details**: Show/hide unchanged attributes

Generate visualization:

```bash
# From a simulation name
uv run sim visualize demo

# Opens automatically with --viz flag
uv run sim simulate --obj flashlight turn_on --viz
```

---

## Development

### Code Style

```bash
# Format code
uv run ruff format src/

# Lint
uv run ruff check src/

# Auto-fix
uv run ruff check --fix src/
```

### Adding Objects or Actions

1. Create YAML in appropriate `kb/` directory
2. Validate: `uv run sim validate --verbose-load`
3. Test: `uv run sim show object <name>`
4. Simulate: `uv run sim simulate --obj <name> <actions>`

---

## Examples

See **[EXAMPLES.md](EXAMPLES.md)** for comprehensive CLI examples.

---

World Simulator provides a clean foundation for simulating object state transitions with deterministic, tree-based execution and visual exploration.
