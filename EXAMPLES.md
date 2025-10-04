# Simulator CLI Examples

This document provides example commands for using the World Simulator CLI.

## 1) Validate and Inspect

```bash
# Validate the knowledge base
uv run sim validate

# Show available behaviors for an object
uv run sim show behaviors flashlight

# Show object definition
uv run sim show object flashlight
```

**Note**: You can now pass multiple actions after a single `--actions` flag. The older repeated form still works if you prefer it.

**Note**: `flashlight.battery.level` default is 'unknown' in the KB. During simulation, you'll be asked for its value when needed.

## 2) Core Simulations

```bash
# Basic flashlight simulation with custom name
uv run sim simulate --obj flashlight --actions turn_on turn_off --name basic_test

# Auto-generated name (timestamp-based)
uv run sim simulate --obj flashlight --actions turn_on turn_off

# View history
uv run sim history outputs/histories/basic_test.yaml
```

**Note**: All simulations show real-time progress automatically:
- Success confirmations: `✅ action_name ran successfully` for each action
- Interactive clarification questions for unknown values
- Summary at the end with file paths and success count

## 3) Failure and Reasoning Evidence

```bash
# Drain battery then try to turn on (will fail)
uv run sim simulate --obj flashlight --actions drain_battery turn_on --name flashlight_fail_test

# View the failure history
uv run sim history outputs/histories/flashlight_fail_test.yaml
```

## 4) Result Text Generation

Result text is automatically saved for each simulate run to `outputs/results/`.

## 5) Interactive Simulation (Stop/Clarify/Continue)

Interactive simulate is the default; unknowns should be defined in YAML defaults.

```bash
uv run sim simulate --obj flashlight --actions turn_on --name turn_on_interactive
```

## Failure Handling Semantics

- **Unknown-driven failure**: If a precondition depends on an unknown value (e.g., `battery.level == unknown`), the CLI will ASK a clarification, set your answer, and RETRY the same action immediately. If it then succeeds, the step is recorded as OK and the state advances.

- **True precondition failure**: If a precondition is not met and no clarification applies, the simulator ALWAYS STOPS the run immediately after recording the failed step. The object state remains unchanged from the last valid state. The dataset text will include the full story, Q/A clarifications (if any), and per-step results including the failure reason.

### Example:

```bash
uv run sim simulate --obj flashlight --actions drain_battery turn_on turn_off --name fail_example
```

If `turn_on` fails (empty battery), the run stops right there. The result shows `turn_on` FAILED and no further actions are executed.

## 6) History Inspection

```bash
# View any saved history file
uv run sim history outputs/histories/basic.yaml
```

## 7) TV Four-Step Sequence (No Q → Q → No Q → FAIL)

Object: TV (`network.wifi_connected` default = unknown)

Actions in a single simulate:
1. `turn_on` → no question (precondition doesn't use unknown) → PASS
2. `open_streaming` → asks for `network.wifi_connected` (unknown) → you answer 'on' → PASS (If you answer anything else, this step FAILS and the run stops.)
3. `adjust_volume` → no question (requires power on and a `to_level` parameter) → PASS
4. `factory_reset` → FAIL (requires `screen.power == off`; it's on) → STOP

```bash
uv run sim simulate --obj tv \
  --actions turn_on open_streaming adjust_volume:to_level=low factory_reset \
  --name tv_advanced

uv run sim history outputs/histories/tv_advanced.yaml
```

**Tip**: `adjust_volume` requires a `to_level` argument. Using the `action:param=value` syntax keeps the value scoped to that action without affecting others.

## 8) TV Flow Without Unknown-Triggered Action

Here we skip `open_streaming`, so no unknown is needed.

```bash
uv run sim simulate --obj tv --actions turn_on adjust_volume --name tv_simple

uv run sim history outputs/histories/tv_simple.yaml
```

## Using the --params Flag

Pass parameters to actions using the `--params` flag:

```bash
# Pour water to a specific level with custom name
uv run sim simulate --obj kettle --actions pour_water --params to_level=medium --name kettle_pour_test

# Invalid parameter value (will fail validation)
uv run sim simulate --obj kettle --actions pour_water --params to_level=overflow --name kettle_invalid
```

---

## Complex Multi-Action Examples

### TV Evening Session (5 Actions, Interactive)

This sequence demonstrates unknown value clarifications and multiple parameters:

```bash
uv run sim simulate --obj tv \
  --actions turn_on open_streaming adjust_volume change_channel turn_off \
  --params to_level=high --params to_channel=medium \
  --name tv_evening_session
```

**What happens:**
1. `turn_on` → Will ask: "What is power source connection?" (unknown) → Answer: **on**
2. `open_streaming` → Will ask: "What is network wifi_connected?" (unknown) → Answer: **on**
3. `adjust_volume` → Sets volume to high (from params)
4. `change_channel` → Will ask: "What is power source voltage?" (unknown) → Answer: **medium** or **high**
5. `turn_off` → Turns everything off

### Kettle Morning Routine (4 Actions)

Complete kettle workflow from empty to boiling:

```bash
uv run sim simulate --obj kettle \
  --actions pour_water turn_on heat turn_off \
  --params to_level=full \
  --name kettle_morning_routine
```

**What happens:**
1. `pour_water` → Fills tank to full
2. `turn_on` → Powers on the kettle
3. `heat` → Heats the water to hot
4. `turn_off` → Powers off when done

### Flashlight Battery Management (5 Actions)

Battery lifecycle with different charging levels:

```bash
# Replace with partial charge
uv run sim simulate --obj flashlight \
  --actions drain_battery turn_off replace_battery turn_on turn_off \
  --params new_level=medium \
  --name flashlight_battery_test
```

**What happens:**
1. `drain_battery` → Drains battery to empty (no precondition check)
2. `turn_off` → Ensures flashlight is off before battery replacement
3. `replace_battery` → Replaces with medium-charged battery
4. `turn_on` → Turns on with medium battery
5. `turn_off` → Powers off

### Multiple Actions with Mixed Parameters

Using action-specific parameters with colon syntax:

```bash
# Each action can have its own parameters using colon syntax
uv run sim simulate --obj kettle \
  --actions pour_water:to_level=low turn_on heat turn_off pour_water:to_level=full \
  --name kettle_refill_sequence
```

**What happens:**
1. First `pour_water` → Fills to low
2. `turn_on` → Powers on
3. `heat` → Heats the water
4. `turn_off` → Powers off
5. Second `pour_water` → Refills to full

### TV with Volume Control Variations

Testing different volume levels:

```bash
# Start quiet, then increase
uv run sim simulate --obj tv \
  --actions turn_on adjust_volume:to_level=mute adjust_volume:to_level=low \
  --actions adjust_volume:to_level=high turn_off \
  --name tv_volume_progression
```

**What happens:**
1. `turn_on` → Powers on TV
2. First `adjust_volume` → Mutes the TV
3. Second `adjust_volume` → Sets to low volume
4. Third `adjust_volume` → Sets to high volume
5. `turn_off` → Powers off
