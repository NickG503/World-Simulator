# Mental Models Simulator (Phase 1)

Ground-truth, qualitative simulator for everyday objects. This repo is built to become a
benchmark generator: *deterministic state transitions over discrete, ordered attribute spaces*.

This package currently implements **Phase 1** (core object model & validation).

## Layout

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
  objects/             # YAML object definitions (flashlight, kettle)
tests/
  test_phase1_smoke.py # Simple sanity checks
```

## Install (editable) & run

```bash
pip install -e .
sim validate
sim show object flashlight --version 1
```

## Authoring new object types

Create `kb/objects/<name>.yaml`:

```yaml
type: flashlight
version: 1
attributes:
  switch:        { space: [off, on],        mutable: true,  default: off }
  bulb:          { space: [off, on],        mutable: true,  default: off }
  battery_level: { space: [empty, low, med, high], mutable: true, default: med }
```

Then run:

```bash
sim validate
```

## Next phases (folders already set up)

- Phase 2: Actions (preconditions/effects) and TransitionResult
- Phase 3: Unknowns & blocked outcomes
- Phase 4: Environment ticks
- Phase 5: Constraints & immutability
- Phase 7: SQLite persistence
- Phase 8: Scenario generator & dataset packaging
```