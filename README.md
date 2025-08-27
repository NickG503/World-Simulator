# Mental Models Simulator — Project Memory & Roadmap (Living Doc)

This repository is a **ground-truth qualitative simulator** for everyday objects, designed
to generate **deterministic, labeled state transitions** for a future benchmark. It is **not**
LLM-facing; it defines what *correct* world updates look like when actions are applied, so
any external model can later be judged against these canonical transitions.

> This README is a **living memory file**: it documents current capabilities, internal
> data structures, authoring conventions, and the full roadmap across phases. Treat it as
> the source of truth for how the simulator works and evolves.

---

## Current Status: **Phase 1 — Core Object Model**
**Goal:** implement immutable, validated definitions of object *types* and concrete *states*, with
human-editable YAML files and a tiny CLI for validation/inspection.

### Components implemented in Phase 1

#### 1) `QuantitySpace`
**Module:** `src/simulator/core/quantity.py`  
Represents an **ordered qualitative value space**, e.g. `["empty", "low", "med", "high"]`.

- **Fields**
  - `name: str` — identifier (e.g., `"flashlight.battery_level"`)
  - `levels: list[str]` — strictly ordered, unique labels (non-empty)

- **Methods**
  - `has(value: str) -> bool` — membership test
  - `clamp(value: str) -> str` — returns `value` if in space; otherwise the first level
  - `step(value: str, direction: "up"|"down"|"none") -> str` — move one step (with clamping at ends)

- **Invariants**
  - `levels` must be non-empty and contain unique strings.
  - `step` never raises on boundary; it returns the boundary value.

#### 2) `AttributeType`
**Module:** `src/simulator/core/attributes.py`  
Defines a **typed attribute** belonging to an `ObjectType`.

- **Fields**
  - `name: str`
  - `space: QuantitySpace` — value domain
  - `mutable: bool = True` — if `False`, the attribute cannot change (enforced in later phases too)
  - `default: Optional[str]` — if omitted, defaults to the **first** level of the `space`

- **Validation**
  - If `default` is specified, it must be inside `space.levels`.

#### 3) `ObjectType`
**Module:** `src/simulator/core/object_types.py`  
Declares a **versioned object template** whose instances share the same attribute schema.

- **Fields**
  - `name: str` (e.g., `"flashlight"`)
  - `version: int` (semantic version step; bump when schema changes)
  - `attributes: dict[str, AttributeType]` — non-empty, all unique keys

- **Methods**
  - `default_state() -> ObjectState` — creates a validated concrete state; each attribute gets
    `attr.default` if present, otherwise the first level in its space.

- **Conventions**
  - Use notation `name@v{version}` in logs and docs (e.g., `flashlight@v1`).

#### 4) `ObjectState`
**Module:** `src/simulator/core/state.py`  
A **concrete instance** of an object type with **current values** (and optional **trends** metadata).

- **Fields**
  - `object_type: ObjectType` — the type this state conforms to
  - `values: dict[str, str]` — **must include exactly** the attributes from `object_type`
  - `trends: dict[str, "up"|"down"|"none"] = {}` — optional metadata for later phases

- **Validation**
  - Every `object_type.attributes` key must be present in `values` and the value must be in the
    attribute’s `QuantitySpace`.
  - No unknown keys are permitted in `values`.

- **Methods**
  - `set_value(attr_name: str, new_value: str)` — validates mutability and domain; intended for
    internal use by transition engines in later phases.

- **Serialization**
  - Pydantic model: `state.model_dump()` yields a JSON-ready structure.

#### 5) `Registry`
**Module:** `src/simulator/core/registry.py`  
In-memory store for **object types**, indexed by `(name, version)`.

- **Methods**
  - `add_object_type(obj_type: ObjectType)` — rejects duplicates
  - `get(name: str, version: int) -> ObjectType`
  - `all() -> Iterable[ObjectType]`

#### 6) YAML Loader (Authoring pipeline)
**Module:** `src/simulator/io/yaml_loader.py`  
Loads all YAML files under `kb/objects/` and constructs a validated `Registry`.

- **YAML Schema (object type)**
  ```yaml
  type: flashlight                   # required
  version: 1                         # required (int)
  attributes:                        # required (mapping, non-empty)
    switch:        { space: [off, on],        mutable: true,  default: off }
    bulb:          { space: [off, on],        mutable: true,  default: off }
    battery_level: { space: [empty, low, med, high], mutable: true, default: med }
  ```

- **Error cases**
  - Missing `type` or `version`
  - Empty or non-mapping `attributes`
  - Attribute without a non-empty `space`
  - `default` not in `space`

#### 7) CLI (Phase 1)
**Module:** `src/simulator/cli/app.py` (entrypoint: `sim`)  
Commands:
- `sim validate` — loads `kb/objects` and validates everything
- `sim show object <name> --version <int>` — prints a table of attributes & default state JSON

#### 8) Tests
**File:** `tests/test_phase1_smoke.py`  
- Loads types, checks spaces/defaults, and verifies that a `default_state()` is valid.

---

## Repository Layout
```
src/simulator/
  core/
    quantity.py        # QuantitySpace (ordered qualitative levels)
    attributes.py      # AttributeType
    object_types.py    # ObjectType
    state.py           # ObjectState
    registry.py        # In-memory registry
  io/
    yaml_loader.py     # Load ObjectType defs from kb/objects/*.yaml
  cli/
    app.py             # CLI: sim validate, sim show object
kb/
  objects/
    flashlight.yaml    # example object type
    kettle.yaml        # example object type
tests/
  test_phase1_smoke.py
pyproject.toml
README.md  (this file)
```

---

## Authoring: Adding or Modifying Object Types
1. Create a new YAML in `kb/objects/` or edit an existing one.
2. Run `sim validate` to catch schema issues.
3. Use `sim show object <name> --version <v>` to inspect the definition.
4. **Versioning:** bump `version` when changing schema (spaces, new attributes, mutability or defaults).

> In Phase 7, you’ll get a migration command to load file definitions into SQLite with
> version history, but **file-first** keeps iteration fast during early development.

---

## Roadmap (Phases 2 → 9)

This roadmap is simulator-only (no LLM features). Each phase is independently shippable.

### Phase 2 — **Actions & Transition Engine (single object)**
**Goal:** Deterministic, file-authored **actions** with preconditions and effects, producing
validated next states and diffs.

- **New concepts**
  - `ActionType`: `name`, `object_type`, `parameters`, `preconditions`, `effects`
  - `TransitionResult`: `{before, after, status, diff, violations=[]}`
  - **Safe DSL** for preconditions/effects (tiny whitelist, no `eval`):
    - Predicates: `==`, `!=`, `in`, `and`, `or`, parentheses
    - Implication: `A -> B` in preconditions (as convenience sugar)
    - Effects statements:
      - assignments: `attr = "value"`
      - conditional: `"cond ? then : else"` or `if cond then ... else ...` (parsed form)
      - trend metadata: `attr trend = "up"|"down"|"none"`
      - single-step moves: `attr inc` / `attr dec` (shortcut for `QuantitySpace.step`)

- **CLI**
  - `sim apply --object <name>@v<ver> --state <path.json> --action <action> --params k=v ...`
  - Prints `TransitionResult` JSON and a human-friendly diff table.

- **Tests**
  - Unit tests per action; golden tests for diffs.

### Phase 3 — **Unknowns & Blocked Outcomes**
**Goal:** Allow attributes with value `unknown` and return **blocked** results when preconditions
touch unknowns (no interactive prompting here; just machine-readable reasons).

- **Changes**
  - Permit `unknown` as a value in `ObjectState.values`.
  - `TransitionResult.status ∈ {"ok", "rejected", "blocked"}`.
  - When `blocked`, include `{"missing": ["attr_a","attr_b"]}` in the result.
  - Helper utility to resolve unknowns in batch to generate complete datasets.

- **CLI**
  - `sim apply` prints the `blocked` reason; `sim resolve --state s.json --set attr=value ...`

### Phase 4 — **Environment Ticks (single object processes)**
**Goal:** Discrete-time **qualitative processes** (e.g., battery drains while on).

- **New concept**
  - `EnvironmentRule`: `{object_type, when: predicate, do: [operations]}`
    - operations include `attr inc/dec`, `attr trend = ...`, or compound rules
- **API**
  - `tick(state, rules) -> state'` applies all matching rules once (with clamping).
- **CLI**
  - `sim tick --object <name>@v<ver> --state <path.json> --rules kb/env/*.yaml --ticks N`

### Phase 5 — **Constraints & Immutability Enforcement**
**Goal:** Enforce invariants and reject impossible states.

- **Features**
  - Hard enforcement of `mutable: false` in transitions.
  - Pluggable `Constraint` checks registered per `ObjectType` (e.g., “`switch==on` ⇒ `bulb==on`”).
  - `violations` listed in `TransitionResult`; can be configured to `reject` or `autofix` (later).

- **CLI**
  - `sim validate constraints` runs checks on a corpus of states.

### Phase 6 — **Authoring Ergonomics & Property Tests**
**Goal:** Smooth content creation and stronger guarantees.

- **CLI helpers**
  - `sim new object <name>` → YAML scaffold
  - `sim new action <object> <name>` → YAML scaffold
  - `sim diff types <name> v1..v2`
  - `sim where-used <object>` → find related actions/rules
- **Testing**
  - Property-based tests (Hypothesis) for ordering/monotonicity on `QuantitySpace` operations.

### Phase 7 — **Persistence: SQLite Backend (optional)**
**Goal:** Versioned storage for types/actions and indexed logs for large rollouts.

- **Schema (JSON-in-SQL)**
  - `object_types(id, name, version, schema_json)`
  - `action_types(id, name, object_type, version, spec_json)`
  - `objects(id, type, created_at)`
  - `states(id, object_id, t, state_json)`
  - `transitions(id, object_id, t, action, before_id, after_id, diff_json, status)`

- **CLI**
  - `sim migrate --from kb --to sim.db`
  - `sim export --from sim.db --to kb`

### Phase 8 — **Scenario Generator & Dataset Packaging**
**Goal:** Produce benchmark-ready rollouts as **JSONL** with strict schemas.

- **APIs**
  - `ScenarioBuilder` — sampling & enumeration of initial states
  - `ActionSequencer` — valid sequences respecting preconditions (`ok/blocked/rejected`)
  - `RolloutWriter` — tuples like:
    ```json
    {
      "object_type": "flashlight@v1",
      "s_t": {...},
      "a_t": {"name": "flip_switch", "params": {"to": "on"}},
      "s_act_t1": {...},
      "s_t1": {...},
      "diff": [["bulb", "off", "on"]],
      "status": "ok"
    }
    ```
- **Determinism**
  - All stochastic choices (if any later) are seeded and logged.

### Phase 9 — **Multi-Object World & (Later) Relations/Parts**
**Goal:** Extend from single-object to world-level transitions (still qualitative).

- **New concepts**
  - `WorldState`: mapping of object IDs → `ObjectState`
  - Multi-object `ActionType` and atomic apply/rollback
  - (Optional, later) `parts`/`relations` on `ObjectType` and cross-object `EnvironmentRule`s

- **CLI**
  - `sim apply-world`, `sim tick-world`, `sim rollout-world`

---

## Conventions & Design Principles

- **Determinism first:** Same input → same output. If randomness is ever introduced, use seeded RNG
  and record seeds in logs.
- **Schema versioning:** Types/actions are referred to as `name@vX`. Bump versions on schema changes.
- **DSL, not eval:** All preconditions/effects use a small, safe DSL (added in Phase 2). No Python `eval`.
- **Strict diffs:** Every transition returns `(attr, old, new)` triplets; this becomes ground truth.
- **File-first authoring:** YAML/JSON while exploring; DB only when scale or versioning demands it.
- **Separation of concerns:** Authoring (YAML) ↔ Loading (io) ↔ Core (models) ↔ Engines (actions/env).

---

## Quickstart (Phase 1)

```bash
pip install -e .
sim validate
sim show object flashlight --version 1
```

**Add a new object**
1) Create `kb/objects/my_object.yaml` following the schema above.  
2) `sim validate` to ensure correctness.  
3) `sim show object my_object --version 1` to inspect defaults.

---

## Changelog (high level)
- **Phase 1**: Introduced core models (QuantitySpace, AttributeType, ObjectType, ObjectState), YAML
  loader, registry, CLI (`validate`, `show object`), example objects (`flashlight@v1`, `kettle@v1`).

(Next: Phase 2 — Actions & Transition Engine)
