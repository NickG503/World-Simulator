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
# Clone the repository
git clone <repository-url>
cd World-Simulator

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

# View the simulation history
uv run sim history outputs/histories/basic_test.yaml
```

**Note**: Simulations are interactive and will prompt you for clarification when encountering unknown attribute values.

### Examples

For comprehensive CLI examples including parameters, clarifications, and advanced features, see **[EXAMPLES.md](EXAMPLES.md)**.

---

## Project Layout

```
src/
  simulator/
    cli/              # Typer-based CLI commands
    io/loaders/       # YAML → typed specs → runtime models
    core/
      actions/        # Action, Condition, Effect types & specs
      objects/        # ObjectType, ObjectInstance, AttributeTarget
      registries/     # RegistryManager + cross-validation
      engine/         # TransitionEngine, ConditionEvaluator, EffectApplier
      simulation_runner.py  # High-level simulation utilities
      dataset/              # Dataset text builders (minimal story + clarifications + results)
kb/
  spaces/            # Qualitative space definitions
  objects/           # Object type YAML files
  actions/           # Generic & object-specific actions
tests/               # Pytest suite covering loaders, smoke tests, behaviour validation
```

---

## Core Components

| Area        | Key Classes | Responsibilities |
|-------------|-------------|------------------|
| Registries  | `RegistryManager`, `RegistryValidator` | Stores qualitative spaces, attributes, objects, and actions. Performs cross-registry validation on attribute references, behaviours, and constraints. |
| Engine      | `TransitionEngine`, `ConditionEvaluator`, `EffectApplier`, `DiffEntry`, `TransitionResult` | Validates parameters, evaluates structured preconditions, applies effects, records diffs, and enforces object-level constraints. |
| Actions     | `Action`, `ActionMetadata`, `ParameterSpec`, `Condition`/`Effect` subclasses | Encapsulate structured action definitions, parameter rules, conditional logic, and effect execution (attribute setters, trend updates, conditional branches). |
| Objects     | `ObjectType`, `PartSpec`, `AttributeSpec`, `ObjectConstraint`, `ObjectBehavior`, `ObjectInstance`, `AttributeTarget` | Describe object structure, defaults, mutability, behaviours, and constraint definitions. Constraints use the same condition language as actions. |
| Simulation  | `ActionRequest`, `AttributeSnapshot`, `ObjectStateSnapshot`, `SimulationStep`, `SimulationHistory`, `SimulationRunner` | Provide typed inputs/outputs for multi-step simulations and produce reusable history artefacts. |
| Dataset     | `build_interactive_dataset_text` | Convert a simulation run into a minimal dataset block with story, clarifications, and per-step results. |

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
| `sim history FILE [--step N]` | Show a step summary table and inline errors for a saved history (use `--step` for a detailed change table at a specific step). |

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

**Current Status**: All 29 tests passing ✓

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
- **Tests** - Runs complete test suite on Python 3.10 and 3.11

CI runs automatically on:
- Every push to `master`
- Every pull request

---

## Project Structure

```
World-Simulator/
├── src/simulator/       # Core simulator code
│   ├── cli/            # Typer-based CLI commands
│   ├── core/           # Engine, actions, objects, registries
│   ├── io/             # YAML loaders
│   └── utils/          # Utilities
├── kb/                 # Knowledge base
│   ├── spaces/         # Qualitative space definitions
│   ├── objects/        # Object type definitions
│   └── actions/        # Action definitions (generic & object-specific)
├── tests/              # Test suite
├── scripts/            # Utility scripts
├── outputs/            # Simulation outputs (histories, results)
└── docs/              # Documentation
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Ensure tests pass: `./scripts/run_all_tests.sh`
5. Ensure formatting is correct: `uv run ruff format . && uv run ruff check .`
6. Commit your changes (pre-commit hooks will run automatically)
7. Push and create a pull request

**Note**: All PRs must pass CI checks (formatting, linting, tests) before merging.

---

## License

[Add your license information here]

---

## Acknowledgments

World Simulator keeps the codebase lean: strong schemas, explicit registries, and a clear runtime pipeline so you can expand the knowledge base or integrate new evaluators with confidence.
