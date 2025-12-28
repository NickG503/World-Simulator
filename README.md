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

## Branching Semantics

The simulator handles uncertainty through systematic branching, exploring all possible outcomes in parallel.

### Simple Conditions

For actions with **simple attribute checks** (single condition on one attribute):

- **Precondition unknown**: 2 branches (success + failure)
- **Postcondition unknown**: N+1 branches (one per if/elif case + one else branch)
- **Both unknown (same attribute)**: Intersection logic reduces total branches

### Compound Conditions (AND/OR)

The simulator supports **compound conditions** that check multiple attributes simultaneously. When compound conditions involve unknown attributes, **De Morgan's law** determines how branches are created.

#### AND Conditions

An AND condition requires **all** sub-conditions to be true:

```yaml
preconditions:
  - type: and
    conditions:
      - { type: attribute_check, target: water_tank.level, operator: not_equals, value: empty }
      - { type: attribute_check, target: bean_hopper.amount, operator: not_equals, value: empty }
      - { type: attribute_check, target: heater.temperature, operator: equals, value: hot }
```

**Branching behavior with unknowns:**

- **Success branch (1)**: All attributes constrained to satisfying values
- **Fail branches (N)**: De Morgan's law: `¬(A ∧ B ∧ C) = ¬A ∨ ¬B ∨ ¬C`
  - One fail branch per unknown attribute, each showing one way the AND can fail

```
Coffee Machine: brew_espresso (water=unknown, beans=unknown, temp=hot)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
    SUCCESS               FAIL (water)          FAIL (beans)
  water ∈ {low,med,high}   water = empty        beans = empty
  beans ∈ {low,med,high}   beans = unknown      water = unknown
```

#### OR Conditions

An OR condition requires **at least one** sub-condition to be true:

```yaml
preconditions:
  - type: or
    conditions:
      - { type: attribute_check, target: reel1.symbol, operator: equals, value: seven }
      - { type: attribute_check, target: reel2.symbol, operator: equals, value: seven }
      - { type: attribute_check, target: reel3.symbol, operator: equals, value: seven }
```

**Branching behavior with unknowns:**

- **Success branches (N)**: One per satisfiable disjunct, each constraining its attribute
- **Fail branch (1)**: De Morgan's law: `¬(A ∨ B ∨ C) = ¬A ∧ ¬B ∧ ¬C`
  - All attributes constrained to their complement values simultaneously

```
Slot Machine: check_any_seven (reel1=unknown, reel2=unknown, reel3=unknown)
                              │
    ┌─────────────────────────┼─────────────────────────┐
    ▼                         ▼                         ▼
SUCCESS (reel1)          SUCCESS (reel2)             FAIL
reel1 = seven            reel2 = seven           reel1 ∈ {cherry,lemon,bar}
                                                 reel2 ∈ {cherry,lemon,bar}
                                                 reel3 ∈ {cherry,lemon,bar}
```

### Comparison Operators

Beyond `equals` and `not_equals`, the simulator supports **comparison operators** on ordered spaces:

| Operator | Meaning | Example Expansion |
|----------|---------|-------------------|
| `>=` | Greater than or equal | `level >= low` → `{low, medium, high, full}` |
| `>` | Greater than | `level > low` → `{medium, high, full}` |
| `<=` | Less than or equal | `level <= medium` → `{empty, low, medium}` |
| `<` | Less than | `level < hot` → `{cold, warm}` |

These operators automatically expand to value sets based on the qualitative space's ordering.

### IN Operator

The `in` and `not_in` operators check membership in a set of values:

```yaml
# Check if symbol is a high-value symbol
- type: attribute_check
  target: reel1.symbol
  operator: in
  value: [seven, bar]
```

When branching on unknown values with `in`:
- **Success branch**: Attribute constrained to the specified set
- **Fail branch**: Attribute constrained to complement of the set

### Flat Conditional Structure

Postcondition effects use a **flat if-elif-else structure**:

```yaml
effects:
  - type: conditional
    condition: { target: battery.level, operator: equals, value: full }
    then: [...]
  - type: conditional
    condition: { target: battery.level, operator: equals, value: high }
    then: [...]
    else: [...]
```

**Note**: Nested conditionals inside `then`/`else` blocks are not recursively branched. Compound conditions at the **top level** of conditionals (e.g., `if (A AND B)`) do branch correctly with full De Morgan application.

### No Clarification Questions

When facing uncertainty, the simulator **always branches** rather than asking for clarification. Every possible outcome is explored in parallel.

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
    attribute: str               # "battery.level" (empty for compound)
    operator: str                # "equals", "in", "not_equals", ">=", "<", etc.
    value: str | List[str]       # "high" or ["low", "medium"]
    source: str                  # "precondition" or "postcondition"
    branch_type: str             # "if", "elif", "else", "success", "fail"
    compound_type: str | None    # "and" or "or" for compound conditions
    sub_conditions: List[BranchCondition] | None  # Parts of compound condition
```

For compound conditions, `attribute` is empty and `sub_conditions` contains the individual attribute checks.

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
- Branching scenarios with unknown values
- Comparison operators (`>=`, `<=`, `>`, `<`)
- AND/OR compound conditions with De Morgan branching
- IN operator for set membership
- Value set exploration
- DAG merging demonstrations

### Quick Examples

```bash
# Coffee machine: AND condition with comparison operators
uv run sim simulate --obj coffee_machine \
  --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=hot \
  --actions brew_espresso --viz

# Slot machine: OR condition (any seven wins)
uv run sim simulate --obj slot_machine \
  --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown \
  --actions check_any_seven --viz

# Comparison operator: temperature < hot
uv run sim simulate --obj coffee_machine \
  --set heater.temperature=unknown --actions heat_up --viz
```

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

Potential expansions for further development:

### Clarification Questions with Pruning

Instead of always branching, detect when the tree would explode and ask the user:

> "The battery level is unknown. Knowing this would reduce branches from 12 to 3. What is the battery level?"

Pruning heuristics could include branch count thresholds, depth limits, or attribute importance scoring based on how many conditions depend on it.

### State Persistence and Continuation

Load a previous simulation's final state (or any node) as the starting point for a new simulation:
- Incremental exploration ("what if I then do X from here?")
- Save/restore simulation checkpoints
- Build on existing scenarios without re-running

### Recursive Nested Conditionals

Currently, nested conditionals inside `else` branches are not recursively branched. For example:

```yaml
effects:
  - type: conditional
    condition: { target: A, ... }
    then: [...]
    else:
      - type: conditional
        condition: { target: B, ... }  # This won't trigger additional branching
        then: [...]
```

Future work could recursively process nested conditionals, creating additional branch layers for each level of nesting.

### Probabilistic Branching

Add probability weights to branches for Monte Carlo simulation:
- Assign probabilities to branch outcomes
- Aggregate statistics across weighted paths
- Support expected value calculations

---

World Simulator provides a clean foundation for exploring object state spaces with deterministic, branching execution and visual exploration.
