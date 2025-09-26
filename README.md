# World Simulator

Robust, deterministic simulator for everyday objects. YAML knowledge bases are parsed into typed models, validated for consistency, and executed to produce canonical state transitions.

---

## Overview

- **Knowledge driven** – qualitative spaces, object definitions, and actions live in `kb/` and are loaded through strict schemas.
- **Explicit runtime** – `TransitionEngine` applies validated actions to object instances while enforcing constraints and recording diffs.
- **Composed history** – simulations and story generation share typed snapshots that downstream tools can narrate or analyse.
- **CLI oriented** – the `sim` command gives high-level entry points (validate, show, apply, simulate, history) with clear error reporting.

---

## Quick Start

```bash
# Install dependencies
uv sync

# Validate the bundled knowledge base
uv run sim validate

# Inspect an object definition
uv run sim show object flashlight

# Apply an action
uv run sim apply flashlight turn_on

# Run a short simulation and save history
uv run sim simulate flashlight "turn_on" "drain_battery" --save outputs/history.yaml
```

Add `--verbose-load` to any command to see full loader validation traces, and `--verbose-run` during simulations for step-by-step logs.

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
      story_generator.py    # Narrative summaries from histories
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
| Narration   | `StoryGenerator`, `ObjectLanguageTemplate` | Convert simulation histories into natural-language stories using the shared snapshot models and recorded diffs. |

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
| `sim show object NAME [--full] [--verbose-load]` | Inspect object definitions, behaviours, and derived defaults. |
| `sim show behaviors NAME` | List behaviour overrides bound to an object. |
| `sim apply OBJECT ACTION [--param key=value] [--verbose-load]` | Instantiate the default object, resolve unknowns, apply an action, and print the resulting diff. |
| `sim simulate OBJECT ACTION... [--save PATH] [--verbose-load] [--verbose-run]` | Execute action sequences, capture typed histories, and persist them. |
| `sim history FILE [--step N] [--action NAME] [--states]` | Explore saved simulation histories interactively. |

Use `--verbose-load` whenever you need the full validation trace for malformed YAML; otherwise, loader errors remain short and user friendly.

---

## Execution Flow

1. **Load** – YAML files are parsed into spec models (`ActionFileSpec`, `ObjectFileSpec`, `QualitativeSpaceFileSpec`).
2. **Build** – Specs construct runtime objects with precompiled constraints and behaviours.
3. **Register** – `RegistryManager` ensures uniqueness and exposes lookup helpers for the engine.
4. **Validate** – `RegistryValidator` traverses action/behaviour/constraint trees, checking attribute targets, mutability, and parameter references.
5. **Execute** – `TransitionEngine` applies actions, emitting `TransitionResult` and `DiffEntry` records for downstream consumers.

---

## Development Notes

- Install tooling with `uv sync`; run tests via `PYTHONPATH=src pytest`.
- Knowledge base additions under `kb/` are validated automatically—use `--verbose-load` while authoring.
- Simulations emit typed histories and can be fed directly into `StoryGenerator` or other analytics pipelines.
- Constraint and behaviour checks run during validation, catching immutable writes or unknown targets before runtime.

---

## Change Log Highlights

- CLI gained `--verbose-load` and `--verbose-run` options for detailed loader traces and simulation logging.
- Core modules now emit logs via Python’s logging framework instead of unguarded prints.
- Simulation and narration utilities operate on typed snapshot models, deprecating the previous ad-hoc helpers.

World Simulator keeps the codebase lean: strong schemas, explicit registries, and a clear runtime pipeline so you can expand the knowledge base or integrate new evaluators with confidence.
