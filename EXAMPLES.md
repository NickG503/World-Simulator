# Simulator CLI Examples

This document provides example commands for using the World Simulator CLI.

---

## Table of Contents

1. [Validation & Inspection](#validation--inspection)
2. [Basic Simulations](#basic-simulations)
3. [Using Parameters](#using-parameters)
4. [Viewing Results](#viewing-results)
5. [Visualization](#visualization)
6. [Multi-Action Sequences](#multi-action-sequences)
7. [Understanding Failures](#understanding-failures)

---

## Validation & Inspection

Before running simulations, validate and inspect your knowledge base:

```bash
# Validate the entire knowledge base
uv run sim validate

# Show object structure
uv run sim show object flashlight
uv run sim show object tv
uv run sim show object kettle

# Show available behaviors
uv run sim show behaviors flashlight
uv run sim show behaviors tv
```

**Example output for `show object flashlight`:**

```
flashlight (Object Type)
Parts: 3, Attributes: 5, Constraints: 1
              Definition
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ Attribute       ┃ Default ┃ Mutable ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ switch.position │ off     │ ✓       │
│ bulb.state      │ off     │ ✓       │
│ bulb.brightness │ none    │ ✓       │
│ battery.level   │ medium  │ ✓       │
│ battery.type    │ AA      │ ✗       │
└─────────────────┴─────────┴─────────┘

Constraints (1):
  1. If bulb.state == on, then battery.level != empty
```

---

## Basic Simulations

### Single Action

Apply one action and see the result:

```bash
# Apply turn_on to flashlight
uv run sim apply flashlight turn_on

# Apply turn_on to TV
uv run sim apply tv turn_on
```

### Simple Sequences

Run multiple actions in sequence:

```bash
# Flashlight on/off cycle
uv run sim simulate --obj flashlight turn_on turn_off --name flashlight_demo

# TV session
uv run sim simulate --obj tv turn_on open_streaming turn_off --name tv_demo

# Kettle workflow
uv run sim simulate --obj kettle pour_water=full heat turn_off --name kettle_demo
```

---

## Using Parameters

Some actions accept parameters to customize behavior.

### Inline Parameter Syntax

Use `action=value` format:

```bash
# Pour specific amount of water
uv run sim simulate --obj kettle pour_water=full --name kettle_full
uv run sim simulate --obj kettle pour_water=medium --name kettle_medium

# Adjust TV volume
uv run sim simulate --obj tv turn_on adjust_volume=high turn_off --name tv_volume

# Change TV channel
uv run sim simulate --obj tv turn_on change_channel=medium turn_off --name tv_channel

# Replace flashlight battery with specific level
uv run sim simulate --obj flashlight replace_battery=high turn_on --name flashlight_new_battery
```

### Multiple Parameters

Each action can have its own parameter:

```bash
# TV with multiple adjustments
uv run sim simulate --obj tv \
  turn_on adjust_volume=low adjust_volume=high change_channel=medium turn_off \
  --name tv_adjustments
```

---

## Viewing Results

### History Command

View simulation results using the history command:

```bash
# View simulation summary
uv run sim history flashlight_demo

# Just use the name - no need for full path or .yaml extension
uv run sim history tv_demo
```

**Example output:**

```
Simulation: flashlight_demo
Object: flashlight
Date: 2025-12-01
Nodes: 3
             Execution Path
┏━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ Node   ┃ Action   ┃ Status ┃ Changes ┃
┡━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ state0 │ Initial  │ ok     │ 0       │
│ state1 │ turn_on  │ ok     │ 4       │
│ state2 │ turn_off │ ok     │ 4       │
└────────┴──────────┴────────┴─────────┘
```

### Detailed View

```bash
# View specific step details
uv run sim history flashlight_demo --step=1

# View all steps in detail
uv run sim history flashlight_demo --all
```

---

## Visualization

Generate interactive HTML visualizations:

```bash
# Generate visualization from existing history
uv run sim visualize flashlight_demo

# Generate visualization and open in browser (default)
uv run sim visualize tv_demo

# Don't auto-open browser
uv run sim visualize kettle_demo --no-open
```

### Auto-Visualization During Simulation

```bash
# Use --viz flag to generate and open visualization automatically
uv run sim simulate --obj flashlight turn_on turn_off --name demo --viz
```

### Visualization Features

The HTML visualization provides:

- **Graph view**: Nodes displayed as circles
- **Click to inspect**: Click any node to see its world state
- **Change highlighting**: Changed attributes shown in gold
- **Relevant attributes**: Attributes involved in the action shown in green
- **Expandable sections**: Show/hide other attributes

---

## Multi-Action Sequences

### Flashlight Battery Cycle

```bash
# Full battery lifecycle
uv run sim simulate --obj flashlight \
  turn_on turn_off turn_on turn_off \
  --name flashlight_cycle
```

### TV Evening Session

```bash
# Complete TV usage scenario
uv run sim simulate --obj tv \
  turn_on open_streaming adjust_volume=high change_channel=medium smart_adjust turn_off \
  --name tv_evening
```

### Kettle Morning Routine

```bash
# Fill, heat, and turn off
uv run sim simulate --obj kettle \
  pour_water=full heat turn_off \
  --name kettle_morning
```

---

## Understanding Failures

### Precondition Failures

Actions fail when preconditions aren't met:

```bash
# Try to change channel while TV is off - will fail
uv run sim simulate --obj tv change_channel=medium --name tv_fail_demo
```

**What happens:**
1. `change_channel` requires `screen.power == on`
2. TV starts with screen off
3. Action is rejected with reason: "Precondition failed"

### Viewing Failed Steps

```bash
# Check the history to see failures
uv run sim history tv_fail_demo
```

Failed steps show status as `rejected` with the failure reason.

### Continuing After Failure

The simulation continues after failures, recording each step:

```bash
# Multiple actions with a failure in the middle
uv run sim simulate --obj tv \
  turn_on turn_off factory_reset turn_on \
  --name tv_with_reset
```

**What happens:**
1. `turn_on` → Success
2. `turn_off` → Success
3. `factory_reset` → Success (screen is off)
4. `turn_on` → Success

---

## Object Reference

### Flashlight

**Parts:** switch, bulb, battery

**Behaviors:**
- `turn_on` - Turn on (requires battery not empty)
- `turn_off` - Turn off
- `replace_battery` - Replace battery (parameter: level)
- `drain_battery` - Drain battery to empty
- `charge_battery` - Charge battery

### TV

**Parts:** button, screen, audio, network, power_source, cooling

**Behaviors:**
- `turn_on` - Power on TV
- `turn_off` - Power off TV
- `open_streaming` - Open streaming app (requires wifi)
- `adjust_volume` - Adjust volume (parameter: level)
- `adjust_brightness` - Adjust brightness
- `change_channel` - Change channel (parameter: channel)
- `premium_mode` - Enable premium mode
- `smart_adjust` - Auto-adjust settings
- `stream_hd` - Stream in HD
- `factory_reset` - Reset to factory settings

### Kettle

**Parts:** tank, heating_element, power

**Behaviors:**
- `pour_water` - Pour water (parameter: level)
- `heat` - Heat the water
- `turn_off` - Turn off
- `drain` - Empty the tank

---

## Tips

1. **Use `--viz` flag** for immediate visual feedback
2. **Name simulations descriptively** for easy reference later
3. **Check behaviors first** with `sim show behaviors <object>`
4. **Validate after KB changes** with `sim validate`
5. **Use history** to understand state changes step by step

---

## Command Reference

```bash
# Validation
uv run sim validate

# Inspection
uv run sim show object <name>
uv run sim show behaviors <name>

# Single action
uv run sim apply <object> <action>

# Simulation
uv run sim simulate --obj <object> <actions...> --name <name>
uv run sim simulate --obj <object> <actions...> --name <name> --viz

# History
uv run sim history <name>
uv run sim history <name> --step=N
uv run sim history <name> --all

# Visualization
uv run sim visualize <name>
uv run sim visualize <name> --no-open
```
