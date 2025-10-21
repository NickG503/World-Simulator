# Simulator CLI Examples

This document provides example commands for using the World Simulator CLI, organized from basic to advanced usage.

---

## Table of Contents

1. [Validation & Inspection](#validation--inspection)
2. [Basic Simulations](#basic-simulations)
3. [Understanding Parameters](#understanding-parameters)
4. [Clarification Questions](#clarification-questions)
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

# View the generated history
uv run sim history outputs/histories/basic_test.yaml
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

## Clarification Questions

The simulator asks clarification questions when it encounters unknown attribute values. This is a key feature for reasoning about incomplete information.

### How Clarifications Work

- **Unknown-driven questions**: If an action depends on an unknown value, the simulator will ask you to clarify it
- **Automatic retry**: After you answer, the action retries automatically
- **State persistence**: Your answers update the object's state for the rest of the simulation

### Two Types of Clarifications

#### Pre-condition Clarification

When an action's **preconditions** check an unknown attribute:

```
Precondition: what is <attribute>?
```

These happen when checking if an action **CAN** run.

**Example:**

```bash
# The change_channel action requires voltage != low as precondition
uv run sim simulate --obj tv turn_on change_channel=high --name tv_precondition_demo
```

You'll see: `Precondition: what is power_source.voltage?`

#### Postcondition Clarification

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

#### Seeing Both Types Together

```bash
# This sequence shows both pre-condition and Postcondition clarifications
uv run sim simulate --obj tv \
  turn_on adjust_brightness change_channel=high \
  --name tv_both_clarifications
```

**Clarifications in this sequence:**
1. **Postcondition**: "Postcondition: what is network.wifi_connected?" (for adjust_brightness)
   - Answer "on" or "off" - both work
2. **Precondition**: "Precondition: what is power_source.voltage?" (for change_channel)
   - Answer "medium" or "high" (not "low" to pass the precondition)

### Key Points

- **Pre-condition clarifications** happen FIRST when checking if an action CAN run
- **Postcondition clarifications** happen AFTER pre-conditions pass, when determining WHAT EFFECTS to apply
- **Both must be satisfied** for an action to succeed
- This enables the simulator to reason about object behavior with incomplete information

### Multiple Unknowns

The simulator can handle **multiple unknown attributes** at once. Instead of stopping at the first unknown, it will:
1. Check ALL preconditions/postconditions
2. Collect ALL unknown attributes
3. Ask you about each one in sequence
4. Retry the action after all are answered

#### Multiple Preconditions Example

```bash
# stream_hd checks multiple unknown attributes in preconditions
uv run sim simulate --obj tv turn_on stream_hd --name tv_multiple_preconditions
```

**What happens:**
1. `turn_on` succeeds
2. `stream_hd` finds TWO unknown attributes in preconditions:
   - `Precondition: what is network.wifi_connected?` → Answer: **on**
   - `Precondition: what is power_source.voltage?` → Answer: **high** or **medium**
3. After answering both, the action retries and succeeds

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

#### Benefits

- **Efficient**: Ask all questions at once rather than retrying multiple times
- **Complete**: Ensures all unknowns are resolved before proceeding
- **Clear**: Shows how many attributes need clarification (e.g., "Precondition requires clarification (2 attribute(s))")

#### Combined Example (Both Types)

```bash
# optimize_viewing has multiple unknowns in BOTH preconditions AND postconditions
uv run sim simulate --obj tv turn_on optimize_viewing --name tv_comprehensive_unknowns
```

**What happens:**
1. `turn_on` succeeds
2. `optimize_viewing` checks preconditions and finds unknowns:
   - `Precondition: what is network.wifi_connected?` → Answer: **on**
   - `Precondition: what is power_source.voltage?` → Answer: **high** or **medium**
3. Preconditions pass, then checks postconditions and finds unknowns:
   - `Postcondition: what is audio.channel?` → Answer: **low**, **medium**, or **high**
   - (Other effect conditions may also ask if their attributes are unknown)
4. After all clarifications, action succeeds with appropriate effects applied

This demonstrates the complete flow: **multiple preconditions** → all answered → **multiple postconditions** → all answered → **success**!

### Smart Short-Circuit Logic (Advanced)

The simulator uses **intelligent short-circuit evaluation** for logical conditions (OR/AND) in postconditions. This means it only asks about unknowns that actually matter for the decision.

**Structure Messages:** Before asking clarification questions, the simulator displays the complete logical structure of the condition, showing you the OR/AND relationships and which attributes are involved. This helps you understand what's being evaluated.

#### Precondition Structure Example

```bash
# stream_hd has multiple preconditions with AND logic
uv run sim simulate --obj tv turn_on stream_hd --name test_precond_structure
```

**What you'll see:**
```
Precondition structure: (network.wifi_connected==on AND power_source.voltage!=low)
Precondition: what is network.wifi_connected?
Precondition: what is power_source.voltage?
```

#### OR Short-Circuit

For `OR` conditions, if the first condition evaluates to TRUE, the simulator **does not** ask about subsequent conditions (they don't matter).

**Example:**

```bash
# test_or_shortcircuit: checks (voltage==high) OR (wifi==on)
# If voltage is high, should NOT ask about wifi
uv run sim simulate --obj tv turn_on test_or_shortcircuit --name test_or_smart
```

**What happens:**
- Shows structure: `Postcondition structure: (power_source.voltage==high OR network.wifi_connected==on)`
- Asks: `Postcondition: what is power_source.voltage?`
- You answer: **high** → First condition is TRUE
- Result: **Does NOT ask** about `network.wifi_connected` (short-circuit!)
- The condition is TRUE, executes `then` branch

**But if you answer differently:**
- You answer: **medium** → First condition is FALSE
- Result: **Now asks** about `network.wifi_connected` (needs to check second condition)

#### AND Short-Circuit

For `AND` conditions, if the first condition evaluates to FALSE, the simulator **does not** ask about subsequent conditions (they don't matter).

**Example:**

```bash
# test_and_shortcircuit: checks (voltage==low) AND (wifi==on)
# If voltage is NOT low, should NOT ask about wifi
uv run sim simulate --obj tv turn_on test_and_shortcircuit --name test_and_smart
```

**What happens:**
- Shows structure: `Postcondition structure: (power_source.voltage==low AND network.wifi_connected==on)`
- Asks: `Postcondition: what is power_source.voltage?`
- You answer: **high** → First condition is FALSE (voltage is NOT low)
- Shows: `→ Set power_source.voltage = high`
- Result: **Does NOT ask** about `network.wifi_connected` (short-circuit!)
- Shows: `⚠ Postcondition evaluated: FALSE → 'else' branch`
- Effects: Sets brightness to **high** (the 'else' branch)

**But if you answer differently:**
- You answer: **low** → First condition is TRUE
- Result: **Now asks** about `network.wifi_connected` (needs ALL conditions for AND)
- After both answered: `✓ Postcondition evaluated: TRUE → 'then' branch`
- Effects: Sets brightness to **low** (the 'then' branch)

#### Benefits of Smart Logic

1. **Efficiency**: Only asks necessary questions
2. **User Experience**: Fewer irrelevant questions
3. **Correctness**: Respects logical evaluation order like programming languages
4. **Smart**: Adapts based on your answers

#### Behavior Summary

| Condition Type | First Result | Asks About Second? | Reason |
|---------------|--------------|-------------------|---------|
| OR | TRUE | ❌ NO | Already true, second doesn't matter |
| OR | FALSE | ✅ YES | Need to check if second is true |
| AND | TRUE | ✅ YES | Need all conditions to be true |
| AND | FALSE | ❌ NO | Already false, second doesn't matter |

This smart evaluation works recursively with nested conditions like `(A OR B) AND (C OR D)`, always asking only what's necessary to determine the outcome.

#### Nested Condition Example

```bash
# test_nested_logic: ((voltage==high) OR (wifi==on)) AND (channel!=low)
uv run sim simulate --obj tv turn_on test_nested_logic --name test_nested
```

**What happens:**
- Shows structure: `Postcondition structure: ((power_source.voltage==high OR network.wifi_connected==on) AND audio.channel!=low)`
- Asks about voltage → Answer: **high** → OR's first part is TRUE
- **Doesn't ask** about wifi (OR short-circuit!)
- AND needs all parts, so asks about channel → Answer: **medium** → TRUE
- Both parts of AND satisfied → Success!

### Required Postconditions (No Else Branch)

Some actions have postconditions **without an 'else' branch**. These act as **requirements** - if the condition is FALSE, the action **FAILS**.

#### When to Use

- **With else branch**: Condition is a decision point (both outcomes valid)
- **Without else branch**: Condition is a requirement (must be TRUE)

#### Example

```bash
# test_required_postcondition: requires (voltage==high AND wifi==on)
# No else branch - if FALSE, action fails
uv run sim simulate --obj tv turn_on test_required_postcondition --name test_required
```

**Scenario 1: Condition TRUE → Success**
- Shows structure: `Postcondition structure: (voltage==high AND wifi==on)`
- Answer voltage: **high** → TRUE
- Answer wifi: **on** → TRUE
- Result: `✓ Postcondition evaluated: TRUE → 'then' branch`
- ✅ **Action succeeds**

**Scenario 2: Condition FALSE → Failure**
- Shows structure: `Postcondition structure: (voltage==high AND wifi==on)`
- Answer voltage: **medium** → FALSE
- AND short-circuits (doesn't ask about wifi)
- Result: ❌ **Action FAILS: "Postcondition failed: FALSE (no 'else' branch defined)"**
- Simulation stops

This allows you to create actions with **strict requirements** in postconditions, similar to preconditions.

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
  → Answer: high (OR satisfied, short-circuit!)

Postcondition structure: (cooling.temperature!=hot AND audio.channel!=low)
Postcondition: what is audio.channel?
  → Answer: medium

✓ Postcondition evaluated: TRUE → 'then' branch
✅ premium_mode ran successfully
```

This demonstrates the complete flow with both precondition and postcondition structures visible!

**Note:** The simulator only asks about **unknown** attributes. In this example:
- `cooling.temperature` has default value "cold" (known) → Evaluated automatically → cold!=hot → TRUE
- `audio.channel` has default value "unknown" → Asked user

If you want to see it ask about BOTH attributes in an AND condition:

```bash
# test_both_unknown_postcond: Both attributes default to unknown
uv run sim simulate --obj tv turn_on test_both_unknown_postcond --name test_both_ask
```

**What you'll see:**
```
Postcondition structure: (power_source.voltage==high AND network.wifi_connected==on)

Postcondition: what is power_source.voltage?
→ Answer: high (TRUE)

Postcondition: what is network.wifi_connected?  ← Asks about second!
→ Answer: on (TRUE)

✓ Postcondition evaluated: TRUE → 'then' branch
```

Both attributes are unknown, so AND asks about both (first is TRUE, needs to check all).

---

## Failure Handling

Understanding how the simulator handles failures is crucial for creating realistic simulations.

### Types of Failures

#### 1. Unknown-Driven Failures

If a precondition depends on an unknown value, the simulator asks for clarification and retries:

```bash
# Battery level is unknown - simulator will ask
uv run sim simulate --obj flashlight turn_on --name flashlight_clarify
```

If the clarification resolves the issue, the action succeeds and is recorded as OK.

#### 2. True Precondition Failures

If a precondition is not met (and no clarification applies), the simulator **STOPS immediately**:

```bash
# Drain battery then try to turn on (will fail)
uv run sim simulate --obj flashlight drain_battery turn_on turn_off --name flashlight_fail_test

# View the failure
uv run sim history outputs/histories/flashlight_fail_test.yaml
```

**What happens:**
1. `drain_battery` → Succeeds, battery is now empty
2. `turn_on` → **FAILS** (empty battery doesn't meet precondition)
3. `turn_off` → **NEVER RUNS** (simulation stops at failure)

The object state remains unchanged from the last valid state.

#### 3. Validation Failures

Invalid parameters fail before execution:

```bash
# Invalid parameter value
uv run sim simulate --obj kettle pour_water=overflow --name kettle_invalid
```

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
uv run sim history outputs/histories/basic_test.yaml

# View specific step (0-based index)
uv run sim history outputs/histories/tv_reset_forced.yaml --step=2
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

# History
uv run sim history <path/to/history.yaml>
uv run sim history <path/to/history.yaml> --step=<N>
```

---

For more details on the knowledge base format, see the main README.md file.
