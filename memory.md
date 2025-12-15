# World Simulator - Project Memory

## Project Overview

A simulation engine for modeling object state transitions using a tree-based execution model. The system allows defining objects with attributes, actions with preconditions and effects, and runs simulations that track state changes through a tree structure.

**Core Technologies:** Python 3.11+, Pydantic, Typer, Rich, PyYAML

**Architecture:** Tree-based simulation where each node represents a world state and edges represent action transitions.

---

## Architectural Decisions Log

### 2024-12-01: Tree-Based Simulation Refactor

**Decision:** Refactored from linear execution to tree-based architecture.

**Rationale:**
- Enable future branching based on unknown attribute values
- Support multiple possible outcomes from a single action
- Prepare for probabilistic simulation paths

**Key Changes:**
1. Removed complex logical conditions (AND/OR/NOT/Implication)
2. Removed interactive questioning system
3. Implemented TreeSimulationRunner with tree data structures
4. Simplified preconditions to binary (pass/fail) checks
5. Postconditions use flat if-elif-else structure on single attribute

**Phase 1 Constraints:**
- All attribute values are known (no unknowns)
- Linear execution (single path through tree)
- Preconditions check ONE attribute (binary result)
- Postconditions check ONE attribute with flat if-elif-else

### 2024-12-01: Phase 2 Branching Implementation

**Decision:** Implemented branching on unknown values with value sets.

**Rationale:**
- Allow simulation to explore multiple possible outcomes
- Support trends creating value sets (e.g., trend down from "medium" → {empty, low, medium})
- Enable more realistic uncertainty modeling

**Key Changes:**
1. `AttributeSnapshot.value` now supports `Union[str, List[str], None]` for value sets
2. Added `_compute_value_set_from_trend()` to calculate possible values from trends
3. Implemented `_create_precondition_branches()` for 2-way branching (success/fail)
4. Implemented `_create_postcondition_branches()` for N+1 branching (if/elif/else)
5. Updated `_process_action` to detect unknowns and trigger branching
6. Updated visualization to display value sets as `{v1, v2, v3}`
7. Added trend arrows (↑/↓) in visualization

**Branching Rules:**
- **Precondition unknown**: Creates 2 branches
  - Success branch: values that satisfy the condition
  - Fail branch: values that violate the condition
- **Postcondition unknown**: Creates N+1 branches
  - One branch per if/elif case with specific value
  - One else branch with remaining values as a set
- **Maximum branches per action**: 2 × (postcondition_cases + 1)

---

## Project Structure

```
World-Simulator/
├── kb/                           # Knowledge Base
│   ├── actions/                  # Action definitions
│   │   ├── generic/             # Generic actions (turn_on, turn_off, heat)
│   │   └── object_specific/     # Object-specific actions
│   │       ├── flashlight/
│   │       ├── kettle/
│   │       └── tv/
│   ├── objects/                  # Object type definitions
│   │   ├── bottle.yaml
│   │   ├── flashlight.yaml
│   │   ├── kettle.yaml
│   │   └── tv.yaml
│   └── spaces/                   # Attribute space definitions
│       └── common.yaml
├── outputs/                      # Simulation outputs
│   ├── histories/               # YAML history files
│   └── results/                 # Text result files
├── src/
│   └── simulator/
│       ├── cli/                  # Command-line interface
│       │   ├── app.py           # Main CLI application
│       │   ├── formatters.py    # Output formatting
│       │   ├── load_helpers.py  # KB loading utilities
│       │   ├── paths.py         # Path resolution
│       │   └── services.py      # CLI service layer
│       ├── core/                 # Core simulation engine
│       │   ├── actions/         # Action system
│       │   │   ├── action.py    # Action class
│       │   │   ├── conditions/  # Condition types
│       │   │   ├── effects/     # Effect types
│       │   │   ├── file_spec.py # YAML parsing
│       │   │   └── specs.py     # Spec builders
│       │   ├── attributes/      # Attribute system
│       │   ├── constraints/     # Constraint system
│       │   ├── engine/          # Transition engine
│       │   │   ├── condition_evaluator.py
│       │   │   ├── context.py
│       │   │   ├── effect_applier.py
│       │   │   └── transition_engine.py
│       │   ├── objects/         # Object system
│       │   ├── registries/      # Component registries
│       │   ├── simulation_runner.py  # Legacy linear runner
│       │   └── tree/            # Tree-based simulation (NEW)
│       │       ├── __init__.py
│       │       ├── models.py    # TreeNode, SimulationTree, WorldSnapshot
│       │       └── tree_runner.py  # TreeSimulationRunner
│       ├── io/                   # I/O operations
│       │   └── loaders/         # YAML loaders
│       ├── repositories/        # Data repositories
│       ├── services/            # Business services
│       ├── utils/               # Utilities
│       └── visualizer/          # HTML visualization generator
│           ├── __init__.py
│           └── generator.py     # Generates interactive HTML from YAML
├── tests/                        # Unit tests
│   ├── test_cli.py              # CLI command tests
│   └── test_tree_simulation.py  # Tree simulation tests
```

---

## Component Breakdown

### Tree Module (`simulator.core.tree`)

**Purpose:** Tree-based simulation execution with branching support

**Components:**

#### `AttributeSnapshot` (simulation_runner.py)
Represents a single attribute's state with value set support.
- `value: Union[str, List[str], None]` - Single value or set of possible values
- `is_value_set()` - Check if value is a list
- `get_value_as_set()` - Get value as Python set
- `get_single_value()` - Get first/only value
- `is_unknown()` - True if None, "unknown", or multi-value set

#### `WorldSnapshot`
Immutable state capture at a point in time.
- `get_attribute_value(path)` - Get value by path (may return list for value sets)
- `get_attribute_trend(path)` - Get trend by path
- `is_attribute_known(path)` - Check if value is known (single definite value)
- `is_attribute_value_set(path)` - Check if value is a set
- `get_single_value(path)` - Get value as single string
- `get_all_attribute_paths()` - List all attributes

#### `TreeNode`
Single node in simulation tree.
- `is_root`, `is_leaf`, `succeeded`, `failed` properties
- `describe()` - Human-readable description
- `get_changed_attributes()` - List of changed attribute paths
- `branch_condition` - BranchCondition that led to this node

#### `BranchCondition`
Describes what condition led to a branch.
- `value: Union[str, List[str]]` - Single value or set (for else branches)
- `branch_type: Literal["if", "elif", "else", "success", "fail"]`
- `is_value_set()` - Check if value is a list
- `get_value_display()` - Format value (handles sets as `{v1, v2}`)
- `describe()` - Human-readable condition
- `matches_value(value)` - Check if value matches

#### `SimulationTree`
Complete tree structure.
- `add_node()`, `add_branch_nodes()` - Node management
- `get_leaf_nodes()`, `get_path_to_node()`, `get_children()`, `get_siblings()` - Traversal
- `get_statistics()` - Depth, width, success/fail counts, branch points

#### `TreeSimulationRunner`
Executes simulations building tree structure.
- `_compute_value_set_from_trend(value, trend, space_id)` - Calculate possible values
- `_create_precondition_branches()` - Create 2 branches for unknown precondition
- `_create_postcondition_branches()` - Create N+1 branches for unknown postcondition
- `_get_postcondition_branch_options()` - Extract if/elif/else cases from action

#### Enums
- `NodeStatus` - ok, rejected, constraint_violated, error
- `BranchSource` - precondition, postcondition

**Interfaces:**
```python
from simulator.core.tree import TreeSimulationRunner, SimulationTree
from simulator.core.simulation_runner import AttributeSnapshot

# Run simulation (with automatic branching on unknowns)
runner = TreeSimulationRunner(registry_manager)
tree = runner.run(object_type="flashlight", actions=[...])

# Access tree statistics
stats = tree.get_statistics()
print(f"Depth: {stats['depth']}, Branches: {stats['branch_points']}")

# Check for value sets
node = tree.nodes["state1"]
value = node.snapshot.get_attribute_value("battery.level")
if isinstance(value, list):
    print(f"Possible values: {value}")

# Work with AttributeSnapshot value sets
attr = AttributeSnapshot(value=["low", "medium"], trend="down")
if attr.is_value_set():
    print(f"Value set: {attr.get_value_as_set()}")

# Save
runner.save_tree_to_yaml(tree, "output.yaml")
```

### Transition Engine (`simulator.core.engine`)

**Purpose:** Apply actions and evaluate state transitions

**Components:**
- `TransitionEngine` - Main engine for action application
- `ConditionEvaluator` - Evaluates preconditions
- `EffectApplier` - Applies action effects
- `EvaluationContext` / `ApplicationContext` - Context for evaluation

**Simplified Logic:**
1. Validate parameters
2. Check preconditions (binary pass/fail)
3. Apply effects (conditional effects select branch)
4. Check constraints

### CLI (`simulator.cli`)

**Purpose:** Command-line interface for simulation

**Commands:**
- `validate` - Validate knowledge base
- `show object <name>` - Show object definition
- `show behaviors <name>` - Show object behaviors
- `apply <object> <action>` - Apply single action
- `simulate --obj <type> <actions...>` - Run simulation (add `--viz` to open visualization)
- `history <file>` - View simulation history summary
- `visualize <file>` - Generate and open HTML visualization

### Visualizer (`simulator.visualizer`)

**Purpose:** Generate interactive HTML visualizations from simulation history files

**Components:**
- `generate_visualization(input_yaml, output_html)` - Generates HTML from YAML
- `open_visualization(html_path)` - Opens in default browser

**Features:**
- Tree-like node visualization with clickable nodes
- Relevant attributes shown in green, others in red (expandable)
- Changes between states highlighted in gold
- Dark theme with gradient backgrounds

**CLI Usage:**
```bash
sim visualize <history.yaml>           # Generate and open
sim visualize <history.yaml> -o out.html  # Custom output path
sim visualize <history.yaml> --no-open    # Don't auto-open browser
```

---

### Registries (`simulator.core.registries`)

**Purpose:** Central storage for all component types

**Components:**
- `RegistryManager` - Central access point
- Object registry - Object type definitions
- Action registry - Action definitions
- Space registry - Attribute space definitions

---

## Future Enhancements

### Phase 3: Probabilistic Branching
- Add probability weights to branches
- Monte Carlo simulation support
- Aggregate statistics across paths

### Completed Features (Dec 2024)

#### Phase 1: Tree Foundation
- [x] Sequential node IDs (state0, state1, state2...)
- [x] Simple date format (YYYY-MM-DD)
- [x] Trend no longer makes values unknown - preserves current value
- [x] HTML visualization generator (`sim visualize <history.yaml>`)
- [x] Graph-based visualization with circle nodes (scalable for branching)
- [x] CLI command displayed in visualization header
- [x] Unit tests for tree simulation
- [x] CI/CD with formatting, linting, KB validation, tests, and integration tests
- [x] Tree statistics API (depth, width, success/fail counts)
- [x] WorldSnapshot helper methods (get_attribute_value, is_attribute_known)
- [x] TreeNode properties (succeeded, failed, change_count)

#### Phase 2: Branching on Unknown Values
- [x] Value set support in AttributeSnapshot (`Union[str, List[str], None]`)
- [x] `_compute_value_set_from_trend()` - trends create value sets
- [x] Precondition branching (2 branches: success/fail)
- [x] Postcondition branching (N+1 branches: if/elif/else)
- [x] `_create_precondition_branches()` implementation
- [x] `_create_postcondition_branches()` implementation
- [x] BranchCondition with value set support
- [x] Visualization displays value sets as `{v1, v2, v3}`
- [x] Trend arrows (↑/↓) displayed in visualization
- [x] Branch type styling (if/elif/else nodes colored differently)
- [x] Comprehensive branching tests (50+ tests)
- [x] Failed branch state propagation - constrained values persist to subsequent actions
- [x] Delta display for failed actions - shows only branch_condition attribute as relevant

### Planned Features
- [ ] Interactive branch exploration in visualization
- [ ] Branch pruning/merging strategies
- [ ] Parallel branch evaluation
- [ ] Export tree as DOT graph format

---

## Usage Examples

### Run a Simple Simulation
```bash
python -m simulator.cli.app simulate --obj flashlight turn_on turn_off
```

### Apply Single Action
```bash
python -m simulator.cli.app apply flashlight turn_on
```

### Validate Knowledge Base
```bash
python -m simulator.cli.app validate
```

### View Object Definition
```bash
python -m simulator.cli.app show object flashlight
```

