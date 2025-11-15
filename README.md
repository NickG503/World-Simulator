# World Simulator

A robust, deterministic simulator for everyday objects with qualitative reasoning. YAML knowledge bases are parsed into typed models, validated for consistency, and executed to produce canonical state transitions.

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## Overview

- **Knowledge driven** – Qualitative spaces, object definitions, and actions live in `kb/` and are loaded through strict schemas
- **Explicit runtime** – `TransitionEngine` applies validated actions to object instances while enforcing constraints and recording diffs
- **Composed outputs** – Simulations produce compact YAML histories and minimal dataset text for downstream evaluation
- **CLI oriented** – The `sim` command gives high-level entry points (validate, show, apply, simulate, history) with clear error reporting
- **Interactive clarifications** – Handles unknown attribute values by asking clarification questions with smart short-circuit logic

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

# Run a simulation (interactive)
uv run sim simulate --obj flashlight turn_on turn_off --name basic_test

# View the simulation history (no need to type outputs/histories or .yaml)
uv run sim history basic_test

# Dump every step detail in one go
uv run sim history basic_test --all

# Inspect a specific step (0-based index)
uv run sim history basic_test --step=1
```

**Note**: Simulations are interactive and will prompt you for clarification when encountering unknown attribute values.

### Examples

For comprehensive CLI examples including parameters, clarifications, and advanced features, see **[EXAMPLES.md](EXAMPLES.md)**.

---

## Project Layout

```
src/simulator/
  cli/              # Typer-based CLI commands
  services/         # Business logic layer (simulation, validation, behavior resolution)
  repositories/     # Data access layer (object, action, space repositories)
  io/loaders/       # YAML → typed specs → runtime models
  core/
    actions/        # Action, Condition, Effect types, specs & registries
    objects/        # ObjectType, ObjectInstance, AttributeTarget
    registries/     # RegistryManager + cross-validation
    engine/         # TransitionEngine, ConditionEvaluator, EffectApplier
    simulation_runner.py  # Multi-step simulation execution
    dataset/        # Dataset text builders
kb/
  spaces/           # Qualitative space definitions
  objects/          # Object type YAML files
  actions/          # Generic & object-specific actions
tests/              # Pytest suite
```

---

## Core Components

| Layer       | Key Classes | Responsibilities |
|-------------|-------------|------------------|
| Services    | `SimulationService`, `ValidationService`, `BehaviorResolverService` | Business logic orchestration for simulations, validation, and action resolution. |
| Repositories | `ObjectRepository`, `ActionRepository`, `SpaceRepository` | Clean data access abstractions over registries. |
| Registries  | `RegistryManager`, `ConditionRegistry`, `EffectRegistry` | Central storage and extensible plugin system for types. |
| Engine      | `TransitionEngine`, `ConditionEvaluator`, `EffectApplier` | Validates parameters, evaluates preconditions, applies effects, enforces constraints. |
| Actions     | `Action`, `Condition`, `Effect`, `ParameterSpec` | Structured action definitions with conditional logic and state changes. |
| Objects     | `ObjectType`, `ObjectInstance`, `ObjectBehavior`, `ObjectConstraint` | Object structure, runtime state, custom behaviors, and validation rules. |
| Simulation  | `SimulationRunner`, `SimulationHistory`, `SimulationStep` | Multi-step execution with state tracking and history persistence. |

Loaders rely on dedicated Pydantic specs (`ActionFileSpec`, `ObjectFileSpec`, `QualitativeSpaceFileSpec`). Validation failures raise `LoaderError`, which attaches the source path and concise error snippets for CLI display.

---

## Knowledge Base Schema

- **Spaces (`kb/spaces/`)** – define ordered qualitative levels (e.g., `binary_state`, `battery_level`).
- **Objects (`kb/objects/`)** – declare parts, attributes, defaults, mutability, constraints, and optional behaviour overrides.
- **Actions (`kb/actions/`)** – encode parameters, preconditions, and composable effects for both generic and object-specific actions.

Conditions share a unified dictionary format supporting logical operators (`and`, `or`, `not`, `implication`) and comparative operators (`equals`, `not_equals`, `lt`, `lte`, `gt`, `gte`). Effects include attribute setters, trend setters, and nested conditional branches.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `sim validate [objs] [--acts] [--verbose-load]` | Load spaces, objects, and actions; run registry validation and report issues with file-aware messaging. |
| `sim show object NAME [--verbose-load]` | Inspect object definitions, behaviours, and derived defaults. |
| `sim show behaviors NAME` | List behaviour overrides bound to an object. |
| `sim apply OBJECT ACTION [--param key=value] [--verbose-load]` | Instantiate the default object, resolve unknowns, apply an action, and print the resulting diff. |
| `sim simulate OBJECT ACTION... [--history-name NAME] [--dataset-name NAME] [--id] [--verbose-load] [--verbose-run]` | Execute action sequences interactively (clarify unknowns), save a compact history and a dataset text. |
| `sim history NAME [--step N \| --all]` | Show a summary, or use `--step`/`--all` for detailed tables. You can pass just the simulation name (e.g., `basic_test`) and the CLI resolves `outputs/histories/<name>.yaml` automatically. |

Use `--verbose-load` whenever you need the full validation trace for malformed YAML; otherwise, loader errors remain short and user friendly.

---

## Execution Flow

1. **Load** – YAML files are parsed into spec models (`ActionFileSpec`, `ObjectFileSpec`, `QualitativeSpaceFileSpec`).
2. **Build** – Specs construct runtime objects with precompiled constraints and behaviours.
3. **Register** – `RegistryManager` ensures uniqueness and exposes lookup helpers for the engine.
4. **Validate** – `RegistryValidator` traverses action/behaviour/constraint trees, checking attribute targets, mutability, and parameter references.
5. **Execute** – `TransitionEngine` applies actions, emitting `TransitionResult` and `DiffEntry` records for downstream consumers.

---

## Testing

### Run All Tests

The test runner performs three checks in sequence:
1. **Code Formatting** - Verifies code is properly formatted
2. **Linting** - Runs ruff linter checks
3. **Tests** - Runs the complete test suite

```bash
# Run complete test suite with formatting and linting checks
./scripts/run_all_tests.sh

# Run with verbose output
./scripts/run_all_tests.sh -v

# Run with coverage report
./scripts/run_all_tests.sh --coverage
```

If formatting or linting fails, the script will exit early with helpful messages on how to fix the issues.

### Run Specific Tests

```bash
# Run specific test file
uv run pytest tests/test_flashlight_turn_off.py

# Run specific test function
uv run pytest tests/test_flashlight_turn_off.py::test_behavior_turn_off_ok -v
```

**Current Status**: All 45 tests passing ✓

---

## Ground Truth Testing

### Overview

The ground truth testing system validates simulator correctness by comparing **fully observable** trajectories against **partially observable** replays. This approach ensures that the simulator handles hidden attributes correctly and asks clarification questions at the right moments.

**Key Concept**: Start with a complete simulation where all states are known. Then replay it with some attributes masked as "unknown" (partially observable). At each step, when the simulator asks for clarification, answer using the fully observable ground truth. The partially observable replay should remain consistent with the ground truth throughout.

### Ground Truth Files

Ground truth files live in `tests/data/ground_truth/` and differ from regular simulation history files in several ways:

```yaml
# tests/data/ground_truth/flashlight_battery_trend_low.yaml

object_name: flashlight
metadata:
  hidden_attributes:
    - battery.level        # Initially unknown to simulator
  tracked_attributes:
    - state
    - bulb.brightness
    
interaction_answers:
  0:                       # Step index
    - [battery.level, low] # Attribute, answer
  1:
    - [battery.level, empty]

steps:
  - action: turn_on
    parameters: {}
    changes:
      - attribute: state
        kind: value
        from: off
        to: on
    # ... full state snapshots at each step
```

**Key Differences from Regular History Files**:

1. **`metadata.hidden_attributes`** - Lists attributes that start as "unknown" and are not revealed until the simulator explicitly asks about them
2. **`interaction_answers`** - Maps step indices to clarification answers, providing the ground truth values when the simulator asks
3. **Complete state tracking** - Every step includes both before and after snapshots with all attribute values (even hidden ones)

### Testing Mechanism

The `test_ground_truth_replay` test (`tests/test_ground_truth_replay.py`) performs the following:

1. **Load Ground Truth** - Parse the fully observable trajectory
2. **Initialize Object** - Create instance with hidden attributes masked as "unknown"
3. **Replay Each Step**:
   - Apply pre-step interaction answers (if simulator didn't ask but ground truth has them)
   - Execute action with clarification loop
   - When simulator asks questions, answer from `interaction_answers`
   - Validate state matches expected snapshot
4. **Enforce Invariants** - Run strict validation checks (see below)
5. **Validate Metadata** - Ensure all expected clarifications occurred

### Enforcement Rules

The test implements two critical enforcement rules to catch subtle bugs:

#### ENFORCEMENT 1: Pre-Clarification Integrity

**Rule**: Hidden attributes must stay `"unknown"` until explicitly clarified.

**Exception**: If an action explicitly sets a hidden attribute value (listed in `changes`), that counts as legitimate clarification.

**What This Catches**:
- Actions that accidentally mutate hidden attributes before asking about them
- Unintended side effects that reveal hidden information
- Pre-clarification drift where values change without the simulator asking

```python
# Example violation:
# Hidden attribute 'battery.level' changes from 'unknown' to 'low'
# BUT action didn't list it in changes AND simulator didn't ask
# → Test fails with detailed message showing when drift occurred
```

#### ENFORCEMENT 2: Post-Clarification Tracking

**Rule**: Once an attribute is clarified, it must always be tracked (never reverts to "unknown" unexpectedly).

**Exception**: Values can become "unknown" when trends change to "up" or "down" (simulator intentionally masks values to force re-clarification). In this case, ground truth must also show "unknown".

**What This Catches**:
- Accidental resets of clarified attributes
- Re-masking bugs where attributes incorrectly revert to "unknown"
- Inconsistencies between trend behavior and expected state

```python
# Example violation:
# Attribute 'battery.level' was clarified to 'medium' at step 0
# At step 3, it becomes 'unknown' again
# No trend change to explain it
# → Test fails showing when attribute was clarified and when it reverted
```

### Metadata Validation

After replay completes, the test validates metadata consistency:

1. **Unused Hidden Attributes** - Warns if attributes marked hidden were never asked about (might indicate outdated metadata)
2. **Missing Clarifications** - Fails if `interaction_answers` exist but were never used (simulator should have asked but didn't)
3. **Unexpected Questions** - Warns if simulator asks about non-hidden attributes (shouldn't need clarification)

### Tracking State

The test maintains sophisticated tracking to provide clear failure messages:

```python
clarified_at_step: dict[str, int]      # When each attribute was first clarified
clarified_values: dict[str, Any]       # What value it had when clarified
actually_asked: set[str]               # Attributes simulator actually asked about
ever_clarified: set[str]               # Attributes that were clarified at any point
```

This enables error messages like:

```
AssertionError: Step 3 (drain_battery): Previously clarified attribute 
'battery.level' reverted to 'unknown'. It was clarified to 'medium' at step 0.
This suggests an accidental reset or re-masking bug.
```

### Why This Works

This testing approach catches bugs that simple end-state validation would miss:

- **Temporal Correctness**: Validates state at every step, not just final state
- **Information Flow**: Ensures hidden information stays hidden until properly revealed
- **Question Timing**: Verifies simulator asks clarification questions at the right moments
- **Consistency**: Guarantees partially observable replay produces same result as fully observable ground truth

### Creating Ground Truth Files

Ground truth files are typically created by:

1. Running a simulation with all attributes visible (fully observable)
2. Identifying which attributes should be initially hidden
3. Recording when the simulator would need to ask about them
4. Using `tests/create_ground_truth_dataset.py` or `scripts/build_ground_truth.py` to generate the test file

The result is a comprehensive test case that validates both the correctness of state transitions and the proper handling of partial observability.

---

## Development

### Setting Up Development Environment

```bash
# Install dependencies including dev tools
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Run pre-commit checks manually
uv run pre-commit run --all-files
```

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

- **ruff format** - Automatic code formatting
- **ruff check** - Linting and code quality checks
- **YAML validation** - Ensures valid YAML syntax
- **File cleanup** - Removes trailing whitespace, ensures newlines at EOF

Hooks run automatically on `git commit`. To bypass (not recommended): `git commit --no-verify`

### Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for both formatting and linting:

```bash
# Format code
uv run ruff format src/ tests/

# Check linting
uv run ruff check src/ tests/

# Auto-fix linting issues
uv run ruff check --fix src/ tests/
```

### Knowledge Base Development

- Knowledge base files live in `kb/` (spaces, objects, actions)
- All YAML is validated automatically - use `--verbose-load` while authoring
- Run `uv run sim validate` after making changes
- See [EXAMPLES.md](EXAMPLES.md) for detailed action/behavior examples

### Adding New Objects or Actions

1. Create YAML definition in appropriate `kb/` subdirectory
2. Run validation: `uv run sim validate --verbose-load`
3. Test manually: `uv run sim show object <name>`
4. Add unit tests if adding new behavior patterns
5. Update EXAMPLES.md with usage examples

---

## Continuous Integration

This project uses GitHub Actions for CI/CD:

- **Formatting Check** - Ensures code is properly formatted
- **Linting** - Runs ruff linter on all Python code
- **Tests** - Runs complete test suite with coverage reporting

CI runs automatically on:
- Every push to `master`
- Every pull request

---

World Simulator keeps the codebase lean: strong schemas, explicit registries, and a clear runtime pipeline so you can expand the knowledge base or integrate new evaluators with confidence.
