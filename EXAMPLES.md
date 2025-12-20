# World Simulator Examples

This document provides examples organized from simple to complex, demonstrating all features of the World Simulator.

## Table of Contents

1. [Basic Commands](#basic-commands)
2. [Simple Linear Simulation](#simple-linear-simulation)
3. [Setting Initial Values](#setting-initial-values)
4. [Branching on Unknown Values](#branching-on-unknown-values)
5. [Advanced Branching with IN Operator](#advanced-branching-with-in-operator)
6. [Same Attribute Branching (Intersection Logic)](#same-attribute-branching-intersection-logic)
7. [Multi-Level Branching (Complex)](#multi-level-branching-complex)
8. [DAG State Deduplication (Node Merging)](#dag-state-deduplication-node-merging)

---

## Basic Commands

### Validate Knowledge Base
```bash
sim validate
```

### Show Object Details
```bash
sim show object flashlight
sim show object dice
sim show object dice_same_attr
```

---

## Simple Linear Simulation

Basic simulations where all values are known - results in linear execution (no branching).

### Flashlight: Turn On and Off
```bash
sim simulate --obj flashlight --actions turn_on turn_off --name flashlight_basic
```

### Flashlight: Multiple Actions
```bash
sim simulate --obj flashlight --actions turn_on turn_off turn_on --name flashlight_multi
```

### View History
```bash
sim history outputs/histories/flashlight_basic.yaml
```

### Generate Visualization
```bash
sim visualize outputs/histories/flashlight_basic.yaml -o outputs/visualizations/flashlight_basic.html
```

---

## Setting Initial Values

Use `--set` to override default attribute values before simulation.

### Flashlight with Low Battery
```bash
sim simulate --obj flashlight --set battery.level=low --actions turn_on turn_off --name flashlight_low
```

### Flashlight with Full Battery
```bash
sim simulate --obj flashlight --set battery.level=full --actions turn_on turn_off --name flashlight_full
```

### Flashlight with Empty Battery (Action Fails)
```bash
sim simulate --obj flashlight --set battery.level=empty --actions turn_on --name flashlight_empty
```
*Note: `turn_on` fails because precondition requires `battery.level != empty`*

---

## Branching on Unknown Values

When an attribute is set to `unknown`, the simulator branches on all possible values.

### Flashlight with Unknown Battery Level
```bash
sim simulate --obj flashlight --set battery.level=unknown --actions turn_on --name flashlight_unknown
```
*Creates branches for each battery level: empty (fail), low, medium, high, full (success with different brightness)*

### Flashlight Unknown Battery - Full Cycle
```bash
sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_off --name flashlight_unknown_cycle
```
*Shows how subsequent actions apply to ALL branches (including the failed one)*

### Visualize Branching
```bash
sim visualize outputs/histories/flashlight_unknown.yaml -o outputs/visualizations/flashlight_unknown.html
```

---

## Advanced Branching with IN Operator

The `in` operator allows checking if a value is in a set of values.

### Dice: Different Attributes for Precondition vs Postcondition

The `dice` object demonstrates:
- **Precondition**: `cube.face IN {3, 5, 6}` (succeeds) / `{1, 2, 4}` (fails)
- **Postcondition**: Branches on `cube.color` (different attribute!)
  - `if color == green` → small prize
  - `elif color == red` → medium prize
  - `elif color IN {yellow, black, white}` → big prize (grouped as value set)

```bash
# With known values (linear)
sim simulate --obj dice --set cube.face=3 cube.color=green --actions check_win --name dice_known

# With unknown face and color - full branching
sim simulate --obj dice --set cube.face=unknown cube.color=unknown --actions check_win --name dice_branching
```

**Expected branches for unknown face + color (4 branches):**
1. ✓ **SUCCESS + green**: `face={3,5,6}`, `color=green` → small prize
2. ✓ **SUCCESS + red**: `face={3,5,6}`, `color=red` → medium prize
3. ✓ **SUCCESS + else**: `face={3,5,6}`, `color={yellow,black,white}` → big prize
4. ✗ **FAIL**: `face={1,2,4}` - precondition failed

### Visualize Dice Branching
```bash
sim visualize outputs/histories/dice_branching.yaml -o outputs/visualizations/dice_branching.html
```

---

## Same Attribute Branching (Intersection Logic)

When the same attribute is checked in both precondition AND postcondition, the simulator computes the intersection.

### Dice Same Attribute: Intersection Demo

The `dice_same_attr` object demonstrates:
- **Precondition**: `cube.face IN {3, 5, 6}` (succeeds) / `{1, 2, 4}` (fails)
- **Postcondition**: `if face == 6` → small prize / `else` → big prize (same attribute!)

```bash
# With known values (linear)
sim simulate --obj dice_same_attr --set cube.face=3 --actions check_win --name dice_same_known

# With unknown face - branching with intersection
sim simulate --obj dice_same_attr --set cube.face=unknown --actions check_win --name dice_same_branching
```

**Expected branches for unknown face (3 branches):**
1. ✓ **SUCCESS + face=6**: specific match → small prize
2. ✓ **SUCCESS + else**: `face={3,5}` (remaining after intersection) → big prize
3. ✗ **FAIL**: `face={1,2,4}` - precondition failed (NOT in {3,5,6})

*Note: The else branch gets `{3,5}` = intersection of pass values `{3,5,6}` minus explicit check `{6}`*

### Visualize Same Attribute Branching
```bash
sim visualize outputs/histories/dice_same_branching.yaml -o outputs/visualizations/dice_same_branching.html
```

---

## Multi-Level Branching (Complex)

This example shows branching happening at multiple levels - each action creates new branches on top of previous branches.

### Flashlight: Double Turn On (Two Levels of Branching)

```bash
sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_on --name flashlight_double_branch
```

**What happens:**
1. **Level 1 (first `turn_on`)**: Battery is unknown → splits into 5 branches by postcondition:
   - battery=full → brightness=high
   - battery=high → brightness=high  
   - battery=medium → brightness=medium
   - battery=low → brightness=low
   - battery=empty → FAIL (precondition)

2. **Level 2 (second `turn_on`)**: Each success branch now has a battery value SET from the trend (e.g., `{empty, low}` when low with trend=down):
   - From battery=full: battery now `{empty, low, medium, high}` (trend down) → splits by postcondition
   - From battery=high: battery now `{empty, low, medium}` (trend down) → splits by postcondition
   - From battery=medium: battery now `{empty, low}` (trend down) → splits
   - From battery=low: battery now `{empty}` → FAIL (precondition: battery != empty)
   - Failed branch: stays failed (world unchanged)

This creates a tree with **25 nodes** showing cascading branches.

### Visualize Multi-Level Branching
```bash
sim visualize outputs/histories/flashlight_double_branch.yaml -o outputs/visualizations/flashlight_double_branch.html
```

### Flashlight: Turn On → Off → On (Three-Action Cycle with Branching)

```bash
sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on --name flashlight_cycle_branch
```

**What happens:**
1. **Action 1 (`turn_on`)**: Battery is unknown → splits into 5 branches by postcondition:
   - battery=full → brightness=high, trend=down
   - battery=high → brightness=high, trend=down
   - battery=medium → brightness=medium, trend=down
   - battery=low → brightness=low, trend=down
   - battery=empty → FAIL (precondition)

2. **Action 2 (`turn_off`)**: Applies to ALL branches (including failed ones):
   - Success branches: bulb turns off, brightness=none, trend cleared
   - Failed branch: stays failed (world unchanged)

3. **Action 3 (`turn_on`)**: Each success branch now has battery constrained by trend (e.g., battery was `high` with `trend=down` → now `{empty, low, medium, high}`):
   - Each branch splits again based on postcondition (if/elif/else on battery level)
   - Branches where battery became `empty` fail the precondition
   - Other branches succeed with varying brightness

This demonstrates how the **trend** mechanism creates value sets that cause branching on subsequent actions.

### Visualize Three-Action Cycle
```bash
sim visualize outputs/histories/flashlight_cycle_branch.yaml -o outputs/visualizations/flashlight_cycle_branch.html
```

---

## DAG State Deduplication (Node Merging)

When multiple branches lead to the **same world state**, the simulator automatically merges them into a single node, converting the tree into a DAG (Directed Acyclic Graph). This reduces node count and shows convergent paths.

### Flashlight 4-Action Cycle (Heavy Merging)

```bash
sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on turn_off --name flashlight_4cycle --viz
```

**What happens:**
- Without merging: Would create ~40+ nodes (exponential growth)
- With merging: Creates only **21 nodes** (~50% reduction)
- Merged nodes show "Merged node (X parents)" in the visualization
- Each parent's changes are shown in separate "Changes from Sx" sections

### Dice Multi-Round Game (Convergence after Reset)

```bash
sim simulate --obj dice_same_attr --set cube.face=unknown --actions check_win reset check_win --name dice_multiround --viz
```

**What happens:**
1. **Action 1 (`check_win`)**: Unknown face → 3 branches (face=6, face={3,5}, face={1,2,4} fails)
2. **Action 2 (`reset`)**: Resets face to '3' and clears prize → ALL branches converge to same state!
3. **Action 3 (`check_win`)**: Only one path forward (merged node with 3 parents)

**Result:** 6 nodes instead of 10 (~40% reduction). State4 shows "Merged node (3 parents)" with different changes from each parent.

### Dice 5-Action Chain (Multi-Layer Merging)

```bash
sim simulate --obj dice_same_attr --set cube.face=unknown --actions check_win reset check_win reset check_win --name dice_5actions --viz
```

**What happens - Merging at MULTIPLE layers:**
1. **Layer 1 (`check_win`)**: 3 branches (face=6, face={3,5}, face={1,2,4} fails)
2. **Layer 2 (`reset`)**: **MERGE** - All 3 branches → 1 node (3 parents)
3. **Layer 3 (`check_win`)**: Branches again → 3 new branches
4. **Layer 4 (`reset`)**: **MERGE AGAIN** - All 3 branches → 1 node (3 parents)
5. **Layer 5 (`check_win`)**: Final branching → 3 outcomes

**Result:** Only **8 nodes** instead of 15+ without merging. Shows merging happening at two separate layers (2 and 4).

### Understanding Merged Node Visualization

When you click a merged node:
- **World State**: Shows the current (identical) world state
- **Changes from S1**: Changes when coming from parent S1
- **Changes from S2**: Changes when coming from parent S2 (may differ!)
- **Changes from S3**: Changes when coming from parent S3

Each parent may have taken a different path to reach the same destination state.

### When Does Merging Happen?

Merging occurs when:
1. Two or more nodes in the **same layer** (same action step)
2. Have **identical world states** (all attribute values and trends match)

Common scenarios:
- **Reset actions** that restore default values
- **Actions with no effects** on failed branches
- **Convergent postcondition branches** with same final state

### Example: Double Merge (Two Visible Merge Points)

This example demonstrates TWO merge points in a single simulation using two independent unknown attributes:

```bash
sim simulate --obj dice_double_merge \
  --set cube.face=unknown cube.color=unknown \
  --actions roll_face reset_face roll_color reset_color \
  --name dice_double_merge
```

**Flow:**
1. **roll_face**: face unknown → 3 branches (state1, state2, state3)
2. **reset_face**: ALL 3 branches merge → state4 🔗 (FIRST MERGE)
3. **roll_color**: color unknown → 3 branches (state5, state6, state7)
4. **reset_color**: ALL 3 branches merge → state8 🔗 (SECOND MERGE)

**Result:** 9 nodes total, 2 merge points visible in visualization

```
state0 ─┬─ S1 ──┐
        ├─ S2 ──┼──→ 🔗 S4 ─┬─ S5 ──┐
        └─ S3 ──┘            ├─ S6 ──┼──→ 🔗 S8
                             └─ S7 ──┘
```

---

## Quick Test All Examples

Run all examples at once:
```bash
./scripts/run_examples.sh
```

This will:
1. Create `outputs/histories/` and `outputs/visualizations/` folders
2. Run all simulations above
3. Generate HTML visualizations for each

---

## CLI Reference

### Simulate Command
```bash
sim simulate --obj <object_type> [--set attr=value ...] --actions <action1> [action2 ...] [--name <id>]
```

Options:
- `--obj`: Object type to simulate (required)
- `--set`: Space-separated list of `attribute=value` pairs to set initial values
- `--actions`: Space-separated list of actions to execute
- `--name`: Simulation ID (optional, auto-generated if not provided)

### Visualize Command
```bash
sim visualize <history_file> [-o output.html] [--no-open]
```

Options:
- `-o`: Output HTML file path
- `--no-open`: Don't automatically open in browser
