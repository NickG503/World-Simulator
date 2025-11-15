# Simulator CLI Examples

This document provides example commands for using the World Simulator CLI, organized from basic to advanced usage.

---

## Table of Contents

1. [Validation & Inspection](#validation--inspection)
2. [Basic Simulations](#basic-simulations)
3. [Understanding Parameters](#understanding-parameters)
4. [Handling Unknowns & Clarifications](#handling-unknowns--clarifications)
5. [Failure Handling](#failure-handling)
6. [History & Results](#history--results)
7. [Complex Multi-Action Examples](#complex-multi-action-examples)
8. [Advanced Features](#advanced-features)

---

## Validation & Inspection

Before running simulations, you can validate and inspect your knowledge base:

```bash
# Validate the knowledge base
uv run sim validate

# Show available behaviors for an object
uv run sim show behaviors flashlight

# Show complete object definition
uv run sim show object flashlight

# Show TV behaviors
uv run sim show behaviors tv
```

---

## Basic Simulations

### Your First Simulation

```bash
# Simple flashlight on/off
uv run sim simulate --obj flashlight turn_on turn_off --name basic_test

# View the generated history (name only is enough)
uv run sim history basic_test
```

**Note**: All simulations show real-time progress automatically:
- Success confirmations: `✅ action_name ran successfully` for each action
- Interactive clarification questions for unknown values
- Summary at the end with file paths and success count

### Simple TV Simulation

```bash
# Turn on TV and adjust volume
uv run sim simulate --obj tv turn_on adjust_volume=medium turn_off --name tv_simple
```

### Kettle Simulation

```bash
# Pour water and heat
uv run sim simulate --obj kettle pour_water=full turn_on heat turn_off --name kettle_simple
```

**Note**: Result text is automatically saved to `outputs/results/` for each simulation.

---

## Understanding Parameters

Many actions require or accept parameters to customize their behavior.

### Parameter Syntax

Use `action=value` to assign parameters inline:

```bash
# Pour water to a specific level
uv run sim simulate --obj kettle pour_water=medium --name kettle_pour_test

# Adjust TV volume to high
uv run sim simulate --obj tv turn_on adjust_volume=high turn_off --name tv_volume_test

# Change channel to specific number
uv run sim simulate --obj tv turn_on change_channel=high --name tv_channel_test
```

### Invalid Parameters

If you provide an invalid parameter value, the action will fail validation:

```bash
# This will fail - 'overflow' is not a valid water level
uv run sim simulate --obj kettle pour_water=overflow --name kettle_invalid
```

### Multiple Actions with Different Parameters

Each action can have its own parameter:

```bash
# Multiple volume adjustments
uv run sim simulate --obj tv \
  turn_on adjust_volume=mute adjust_volume=low adjust_volume=high turn_off \
  --name tv_volume_progression
```

---

## Handling Unknowns & Clarifications

Unknown values are intentional—they model partially observable worlds. When an action needs a value you haven’t provided yet, the simulator pauses, asks the missing question, records your answer, and retries the step automatically. Keep in mind:

- Questions appear only when an attribute is unknown *at the moment it matters*.
- Answers persist, so later actions reuse what you told the simulator.
- Every question/answer pair is saved to the history file for later review.

### Pre-condition Clarification

When an action's **preconditions** check an unknown attribute:

```
Precondition: what is <attribute>?
```

These happen when checking if an action **CAN** run.

**Example:**

```bash
# stream_hd requires wifi to be on before it can run
uv run sim simulate --obj tv turn_on stream_hd --name tv_precondition_demo
```

You'll see: `Precondition: what is network.wifi_connected?`

> `turn_on` automatically sets `power_source.connection = on`, so the second half of the AND condition is already satisfied. If you start from a state where that attribute is unknown (for example, by loading a saved history before the TV was powered), you'll receive a second prompt.

### Postcondition Clarification

When an action's **conditional effects** check an unknown attribute:

```
Postcondition: what is <attribute>?
```

These happen when determining **WHAT EFFECTS** to apply.

**Example:**

```bash
# The adjust_brightness action checks network.wifi_connected only in effects
uv run sim simulate --obj tv turn_on adjust_brightness --name tv_Postcondition_demo
```

You'll see: `Postcondition: what is network.wifi_connected?`

### Seeing Both Types Together

```bash
# This sequence shows both pre-condition and postcondition clarifications
uv run sim simulate --obj tv \
  turn_on stream_hd smart_adjust \
  --name tv_both_clarifications
```

**Clarifications in this sequence:**
1. **Precondition** (from `stream_hd`): `Precondition: what is network.wifi_connected?`
   - Provide the wifi status so the action can start (the power connection is already satisfied by `turn_on`).
2. **Postcondition** (from `smart_adjust`): "Postcondition: what is network.wifi_connected?" followed by "Postcondition: what is power_source.voltage?"
   - Your answers determine which branch of the effect runs.

### Multiple Unknowns

The simulator can handle **multiple unknown attributes** at once. Instead of stopping at the first unknown, it will:
1. Check ALL preconditions/postconditions
2. Collect ALL unknown attributes
3. Ask you about each one in sequence
4. Retry the action after all are answered

#### Multiple Preconditions Example

```bash
# stream_hd checks multiple attributes, but only wifi is unknown by default
uv run sim simulate --obj tv turn_on stream_hd --name tv_multiple_preconditions
```

**What happens:**
1. `turn_on` succeeds (and auto-connects the power source)
2. `stream_hd` asks for a single unknown precondition:
   - `Precondition: what is network.wifi_connected?` → Answer: **on**
3. After answering, the action retries and succeeds
4. If you manually clear the power connection (for example, by restoring a saved state before the TV was powered), the simulator would prompt for that attribute as well because the AND condition would have two unknowns.

#### Multiple Postconditions Example

```bash
# smart_adjust checks multiple unknown attributes in effect conditions
uv run sim simulate --obj tv turn_on smart_adjust --name tv_multiple_postconditions
```

**What happens:**
1. `turn_on` succeeds
2. `smart_adjust` finds TWO unknown attributes in effect conditions:
   - `Postcondition: what is network.wifi_connected?` → Answer: **on** or **off**
   - `Postcondition: what is power_source.voltage?` → Answer: **high**, **medium**, or **low**
3. The effects are applied based on your answers

#### Combined Example (Both Types)

You can experience both clarification phases in a single run by chaining two realistic actions:

```bash
uv run sim simulate --obj tv turn_on stream_hd smart_adjust --name tv_pre_post_combo
```

**What happens:**
1. `turn_on` succeeds.
2. `stream_hd` pauses for the wifi precondition (and would also ask about the power connection if you started from a state where it wasn't already satisfied). Once resolved, it boosts the video settings.
3. `smart_adjust` immediately follows, and its conditional effects ask about wifi and voltage to decide how to tune brightness and volume.
4. The result file clearly separates which questions came from preconditions versus postconditions.

That single command shows the flow end-to-end: **unknown preconditions** → resolved → **unknown postconditions** → resolved → **success**.

#### Flashlight Battery Clarification (Postcondition)

```bash
uv run sim simulate --obj flashlight turn_on --name flashlight_battery_question
```

**What happens:**
1. The physical action (flipping the switch) always succeeds and is applied immediately.
2. The simulator then asks `Postcondition: what is battery.level?` because the brightness logic needs that value.
3. If you answer **high/medium/low**, the light turns on with the matching brightness and the battery trend moves downward.
4. If you answer **empty**, the conditional effect runs its `else` branch, leaving the bulb dark—yet the action still succeeds, so you can follow up with `turn_off` or `replace_battery` without restarting the run.

### Smart Short-Circuit Logic (Advanced)

The simulator uses **intelligent short-circuit evaluation** for logical conditions (OR/AND). It only asks about the attributes that actually influence the final result.

**Structure Messages:** Before prompting, the CLI prints the entire logical structure so you can see how the checks are combined.

#### Precondition Structure Example

```bash
# stream_hd has multiple preconditions with AND logic
uv run sim simulate --obj tv turn_on stream_hd --name test_precond_structure
```

**What you'll see (by default):**
```
Precondition structure: (network.wifi_connected==on AND power_source.connection==on)
Precondition: what is network.wifi_connected?
```

`turn_on` satisfies the connection requirement, so only wifi needs clarification unless you intentionally reset `power_source.connection`.

#### Logic Walkthrough Examples

- **Precondition (AND)** — `uv run sim simulate --obj tv turn_on stream_hd --name tv_precond_and`  
  Structure: `(network.wifi_connected==on AND power_source.connection==on)`. By default you'll only be asked about wifi because the connection is already satisfied, but the AND relationship is still visible. If you start from a saved state where `power_source.connection` is unknown, both prompts appear.
- **Precondition (OR)** — `uv run sim simulate --obj tv turn_on premium_mode --name tv_precond_or`  
  Structure: `(power_source.voltage==high OR network.wifi_connected==on)`. If the first attribute is TRUE (voltage=high), the simulator never asks about wifi; otherwise it immediately asks for wifi to see if the OR condition can still pass.
- **Postcondition (AND)** — `uv run sim simulate --obj tv turn_on premium_mode --name tv_postcond_and`  
  Structure: `(cooling.temperature!=hot AND audio.channel!=low)`. If you answer `cooling.temperature = hot`, the AND fails immediately and the `else` branch runs; otherwise it asks about `audio.channel` before applying the correct branch.

#### OR Short-Circuit

`premium_mode` has a precondition `(power_source.voltage==high OR network.wifi_connected==on)`. Run:

```bash
uv run sim simulate --obj tv turn_on premium_mode --name tv_or_shortcircuit
```

- When the prompt asks for `power_source.voltage`, answer **high** → the OR is already TRUE, so it never asks about wifi.
- If you answer **medium**, the first branch is FALSE, so it immediately asks for `network.wifi_connected` to see if the second branch can rescue the condition.

#### AND Short-Circuit

The same `premium_mode` action has an effect condition `(cooling.temperature!=hot AND audio.channel!=low)` with a fallback branch. Run:

```bash
uv run sim simulate --obj tv turn_on premium_mode --name tv_and_shortcircuit
```

- When the postcondition asks for `cooling.temperature`, answer **hot**. The first clause becomes FALSE, so it never asks about `audio.channel`.
- Re-run and answer **cold**. Now the first clause is TRUE, so it immediately asks about `audio.channel` before deciding which branch to use.

#### Behavior Summary

| Condition Type | First Result | Asks About Second? | Reason |
|---------------|--------------|-------------------|---------|
| OR | TRUE | ❌ NO | Already true, second doesn't matter |
| OR | FALSE | ✅ YES | Need to check if second is true |
| AND | TRUE | ✅ YES | Need all conditions to be true |
| AND | FALSE | ❌ NO | Already false, second doesn't matter |

This logic nests, so complicated expressions like `(A OR B) AND (C OR D)` only query the attributes that matter.

### Postconditions Always Provide Outcomes

Every conditional effect now has an explicit `else` branch, so once an action passes its preconditions it always finishes successfully. Instead of failing, the simulator simply chooses the branch that matches your answers.

Example with `premium_mode`:

```bash
uv run sim simulate --obj tv turn_on premium_mode --name tv_branch_choice
```

- If you answer `cooling.temperature = cold` and `audio.channel = medium`, the postcondition evaluates TRUE and sets brightness/volume to **high**.
- If you answer `audio.channel = low`, the same postcondition evaluates FALSE and the `else` branch sets both attributes to **medium**.

Either way, the action succeeds and records which branch ran.

### Complete Example: Both Pre and Post Structures

```bash
# premium_mode shows BOTH precondition and postcondition structures
uv run sim simulate --obj tv turn_on premium_mode --name demo_both_structures
```

**What you'll see:**
```
✅ turn_on ran successfully

Precondition structure: (power_source.voltage==high OR network.wifi_connected==on)
Precondition: what is power_source.voltage?
  → Answer: high (OR satisfied immediately)

Postcondition structure: (cooling.temperature!=hot AND audio.channel!=low)
Postcondition: what is cooling.temperature?
  → Answer: cold (TRUE)
Postcondition: what is audio.channel?
  → Answer: medium (TRUE)

✓ Postcondition evaluated: TRUE → 'then' branch
✅ premium_mode ran successfully
```

If you answer differently (e.g., set `audio.channel` to **low**), the postcondition evaluates FALSE, runs the `else` branch, and the simulation continues without error.

---

## Failure Handling

Understanding how the simulator handles failures is crucial for creating realistic simulations.

### Types of Failures

#### 1. Unknown-Driven Clarifications

Whenever an action needs an unknown attribute (whether in a precondition or inside its effects), the simulator pauses, asks for the value, and then continues without marking the step as failed.

```bash
# Battery level is unknown - simulator will ask during the postcondition
uv run sim simulate --obj flashlight turn_on --name flashlight_clarify
```

After you answer, the action completes successfully and records whichever branch ran.

#### 2. True Precondition Failures

If a precondition is not met (and no clarification applies), the simulator now shows the failure reason **and asks whether you want to continue**. Choosing `Y` logs the failed step and moves on; choosing `N` ends the run immediately.

```bash
# Trying to change the channel while the TV is still off
uv run sim simulate --obj tv change_channel=medium --name tv_precondition_fail

# View the failure
uv run sim history tv_precondition_fail
```

**What happens:**
1. `change_channel` runs first, but its precondition (`screen.power == on`) is FALSE because the TV starts off.
2. The CLI prints `Precondition failed (screen.power==on): screen.power should be on, but got off` and asks if you'd like to continue.
3. Answer **N** to stop immediately, or **Y** to keep going (the failure is recorded with zero effects so the state is unchanged).

#### 3. Validation Failures

Invalid parameters fail before execution:

```bash
# Invalid parameter value
uv run sim simulate --obj kettle pour_water=overflow --name kettle_invalid
```

#### 4. Conditional Effect Branches

Conditional effects always include an `else` branch, so after preconditions succeed an action will never fail because a postcondition couldn't pick a branch. The simulator simply records which branch ran (or that no changes were needed) and moves on.

### Failure Examples

#### TV Factory Reset Failure

```bash
# Try to reset while TV is on (will fail)
uv run sim simulate --obj tv turn_on factory_reset --name tv_reset_blocked
```

The `factory_reset` requires the screen to be off, so this fails.

#### Multi-Step with Failure

```bash
# Multiple actions with a failure in the middle
uv run sim simulate --obj tv \
  turn_on open_streaming adjust_volume=low factory_reset \
  --name tv_advanced
```

**What happens:**
1. `turn_on` → Success
2. `open_streaming` → Will ask for wifi_connected, then succeed
3. `adjust_volume` → Success
4. `factory_reset` → **FAILS** (screen.power is on) → **STOP**

---

## History & Results

Every simulation automatically saves two files:

1. **History YAML**: Complete state transitions and Q&A interactions
2. **Result Text**: Human-readable summary

### Viewing History

```bash
# View complete history
uv run sim history basic_test

# View specific step (0-based index)
uv run sim history tv_reset_forced --step=2
```

### History Format

History files use a compact v3 format:
- Single initial state snapshot
- Per-step deltas (changes only)
- Q&A interactions for clarifications

This keeps files concise while preserving all information for reconstruction.

### Result Files

Result text files are saved to `outputs/results/` and contain:
- Action sequence
- State changes
- Success/failure status
- Clarification Q&A

---

## Complex Multi-Action Examples

### TV Evening Session

A complete TV usage scenario with multiple interactions:

```bash
uv run sim simulate --obj tv \
  turn_on open_streaming adjust_volume=high change_channel=medium turn_off \
  --name tv_evening_session
```

**What happens:**
1. `turn_on` → Powers on TV
2. `open_streaming` → Asks for wifi_connected → Answer: **on**
3. `adjust_volume` → Sets volume to high
4. `change_channel` → Sets channel to medium
5. `turn_off` → Powers everything off

### Kettle Morning Routine

Complete kettle workflow from empty to boiling:

```bash
uv run sim simulate --obj kettle \
  pour_water=full turn_on heat turn_off \
  --name kettle_morning_routine
```

**What happens:**
1. `pour_water` → Fills tank to full
2. `turn_on` → Powers on the kettle
3. `heat` → Heats the water to hot
4. `turn_off` → Powers off when done

### Flashlight Battery Management

Battery lifecycle with replacement:

```bash
uv run sim simulate --obj flashlight \
  drain_battery turn_off replace_battery=medium turn_on turn_off \
  --name flashlight_battery_test
```

**What happens:**
1. `drain_battery` → Drains battery to empty
2. `turn_off` → Ensures flashlight is off before replacement
3. `replace_battery` → Installs medium-charged battery
4. `turn_on` → Turns on with new battery
5. `turn_off` → Powers off

### Flashlight Trend Clarification

Check the filtered clarification options after the battery drains from repeated use:

```bash
uv run sim simulate --obj flashlight replace_battery=high turn_on turn_off turn_on --name flashlight_battery_trend_high
uv run sim simulate --obj flashlight replace_battery=medium turn_on turn_off turn_on --name flashlight_battery_trend_medium
uv run sim simulate --obj flashlight replace_battery=low turn_on turn_off turn_on --name flashlight_battery_trend_low
```

During the final `turn_on` you'll be prompted for `battery.level`; the previous level is excluded from the menu, so pick any of the lower options when the clarification appears.

### Flashlight Battery Charging (Trend Up)

See the upward trend constraints without clarifying after the drain:

```bash
uv run sim simulate --obj flashlight \
  replace_battery=medium turn_on turn_off charge_battery \
  --name flashlight_charge_trend_up

# Inspect the turn_off step (battery is unknown, still trending down)
uv run sim history flashlight_charge_trend_up --step=2

# Inspect the charge step (trend flips to up; options are now ≥ previous level)
uv run sim history flashlight_charge_trend_up --step=3
```

During `charge_battery` you'll first be asked to pick the actual battery level (using the constrained options from step 2). Once you answer, Step 3 overwrites the constraint to `medium, high, full`, demonstrating how the upward charge trend changes the clarification menu immediately after your choice.

### Down → Up Trend Transition In One Run

Combine both directions and trigger the clarification again to see the constrained menu update:

```bash
uv run sim simulate --obj flashlight \
  replace_battery=medium turn_on turn_off charge_battery turn_on \
  --name flashlight_trend_flip_demo

# Watch the state evolve
uv run sim history flashlight_trend_flip_demo --step=1
uv run sim history flashlight_trend_flip_demo --step=3
uv run sim history flashlight_trend_flip_demo --step=4
```

- Step 1 (`turn_on`) drains the battery and marks it `unknown` with a downward constraint.
- Step 3 (`charge_battery`) flips the trend upward while the value is still unknown.
- Step 3 also forces a clarification before it can run, so you select the actual value (e.g., `low`) and the trend switches to `up`.
- Step 4 (`turn_on`) asks you to clarify `battery.level` again, but now the prompt only offers `medium`, `high`, or `full`, confirming that the charge action overwrote the earlier downward constraint based on your previous answer.

Need a longer trace? Extend the sequence and render every step at once:

```bash
uv run sim simulate --obj flashlight \
  replace_battery=medium turn_on turn_off charge_battery turn_on turn_off turn_on \
  --name flashlight_trend_long_demo

# Show the entire history table plus each step's detail
uv run sim history flashlight_trend_long_demo
```

The `uv run sim history … --all` option will print every step detail sequentially, so you can scan the full timeline without re-running the command for each `--step=N`. Use plain `uv run sim history <simulation_name>` for a quick summary (no need to type `outputs/histories/` or `.yaml`), `--all` for full detail, or `--step=N` for targeted inspection.

### Kettle Refill Sequence

Multiple actions with the same action name but different parameters:

```bash
uv run sim simulate --obj kettle \
  pour_water=low turn_on heat turn_off pour_water=full \
  --name kettle_refill_sequence
```

**What happens:**
1. First `pour_water` → Fills to low
2. `turn_on` → Powers on
3. `heat` → Heats the water
4. `turn_off` → Powers off
5. Second `pour_water` → Refills to full

---

## Advanced Features

### OR Preconditions (Forced Actions)

Some actions support multiple paths to success using OR logic in preconditions.

#### Factory Reset Example

The `factory_reset` action can run in two ways:
1. **Normal path**: TV is already off
2. **Forced path**: Using `force=force` parameter

```yaml
preconditions:
  OR:
    - AND:
        - type: attribute_check
          target: screen.power
          operator: equals
          value: off
        - type: attribute_check
          target: button.state
          operator: equals
          value: off
    - type: parameter_equals
      parameter: force
      value: force
```

**Try both flows:**

```bash
# Normal reset (fails because TV is on)
uv run sim simulate --obj tv turn_on factory_reset --name tv_reset_blocked

# Forced reset (succeeds with override)
uv run sim simulate --obj tv turn_on factory_reset=force --name tv_reset_forced
```

The first run stops because the screen is still on; the second succeeds thanks to the forced branch.

### Complex Logical Conditions

You can nest `AND`/`OR` blocks to express complex logic:
- `(cond1 AND cond2) OR (cond3 AND cond4)`
- Multiple layers of nesting
- Mix attribute checks and parameter checks

---

## Tips & Best Practices

1. **Start Simple**: Begin with single-action simulations before building complex sequences
2. **Use Meaningful Names**: Name your simulations descriptively (e.g., `flashlight_battery_test`)
3. **Check Behaviors First**: Use `show behaviors` to see what actions are available
4. **Validate Your KB**: Run `validate` to catch errors before simulating
5. **Review Histories**: Use `history` command to understand state changes
6. **Handle Unknowns**: Many attributes default to 'unknown' - you'll be prompted to clarify them
7. **Learn from Failures**: Failed simulations are valuable for understanding preconditions

---

## Summary of Commands

```bash
# Validation
uv run sim validate

# Inspection
uv run sim show behaviors <object>
uv run sim show object <object>

# Simulation
uv run sim simulate --obj <object> <action1> <action2> --name <name>

# With parameters
uv run sim simulate --obj <object> <action>=<value> --name <name>

# History (name or path; extension optional)
uv run sim history <history_name_or_path>
uv run sim history <history_name_or_path> --step=<N>
uv run sim history <history_name_or_path> --all
```

---

For more details on the knowledge base format, see the main README.md file.
