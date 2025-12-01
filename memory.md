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

**Purpose:** Tree-based simulation execution

**Components:**
- `WorldSnapshot` - Immutable state capture at a point in time
  - `get_attribute_value(path)` - Get value by path
  - `get_attribute_trend(path)` - Get trend by path
  - `is_attribute_known(path)` - Check if value is known (for Phase 2)
  - `get_all_attribute_paths()` - List all attributes
- `TreeNode` - Single node in simulation tree
  - `is_root`, `is_leaf`, `succeeded`, `failed` properties
  - `describe()` - Human-readable description
  - `get_changed_attributes()` - List of changed attribute paths
- `BranchCondition` - Describes what condition led to a branch
  - `describe()` - Human-readable condition
  - `matches_value(value)` - Check if value matches (for Phase 2)
- `SimulationTree` - Complete tree structure
  - `add_node()`, `add_branch_nodes()` - Node management
  - `get_leaf_nodes()`, `get_path_to_node()` - Traversal
  - `get_statistics()` - Depth, width, success/fail counts
- `TreeSimulationRunner` - Executes simulations building tree structure
  - Extension points for Phase 2 branching
- `NodeStatus`, `BranchSource` - Enums for type safety

**Extension Points for Phase 2:**
```python
# In TreeSimulationRunner:
_get_unknown_precondition_attribute()   # Detect branching need
_get_unknown_postcondition_attribute()  # Detect branching need
_get_postcondition_branch_options()     # Get branch options (TODO)
```

**Interfaces:**
```python
from simulator.core.tree import TreeSimulationRunner, SimulationTree

runner = TreeSimulationRunner(registry_manager)
tree = runner.run(object_type="flashlight", actions=[...])

# Access tree statistics
stats = tree.get_statistics()
print(f"Depth: {stats['depth']}, Success: {stats['successful_actions']}")

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

### Phase 2: Branching on Unknown Values
- When precondition has unknown attribute → split into success/fail branches
- When postcondition has unknown attribute → split by each option value
- Tree structure supports multiple children per node

### Phase 3: Probabilistic Branching
- Add probability weights to branches
- Monte Carlo simulation support
- Aggregate statistics across paths

### Completed Features (Dec 2024)
- [x] Sequential node IDs (state0, state1, state2...)
- [x] Simple date format (YYYY-MM-DD)
- [x] Trend no longer makes values unknown - preserves current value
- [x] HTML visualization generator (`sim visualize <history.yaml>`)
- [x] Graph-based visualization with circle nodes (scalable for branching)
- [x] CLI command displayed in visualization header
- [x] Unit tests for tree simulation (46 tests covering Phase 2 APIs)
- [x] CI/CD with formatting, linting, KB validation, tests, and integration tests
- [x] Tree statistics API (depth, width, success/fail counts)
- [x] WorldSnapshot helper methods (get_attribute_value, is_attribute_known)
- [x] TreeNode properties (succeeded, failed, change_count)

### Planned Features
- [ ] New `BranchEffect` type for explicit if-elif-else chains
- [ ] Branch pruning/merging strategies
- [ ] Parallel branch evaluation

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

