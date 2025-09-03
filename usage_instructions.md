# 🌟 Mental Models Simulator: Complete Usage Guide

**Unified Language Architecture for Qualitative Simulations**

This guide explains the **unified YAML language** for defining qualitative simulations in the Mental Models Simulator. Everything uses the same structured condition language - no legacy syntax, no inconsistencies.

> 💡 **Quick Start**: Run `uv run sim validate` to verify your system is working with the unified structured conditions.

## 🏗️ System Architecture

The simulator uses a **three-tier architecture** where each tier communicates through structured references:

```
Qualitative Spaces ──reference──▶ Object Types ──reference──▶ Actions
       ↑                             ↓
       └─────────── validate ────────┘
```

- **Spaces** define value domains (what values are possible)
- **Objects** define structure using spaces (what things exist)  
- **Actions** define transitions using objects (what can change)

**See it in action:**
```bash
# Explore the architecture with real objects
uv run sim show object flashlight
uv run sim show capabilities flashlight
```

This shows parts-based architecture, structured constraints, and automatic capability detection that enables generic actions to work across different object types.

## 📁 Directory Structure

```
kb/
├── spaces/           # Qualitative value domains
│   └── common.yaml
├── objects/          # Object type definitions
│   ├── flashlight.yaml
│   ├── kettle.yaml
│   └── bottle.yaml
└── actions/          # State transition rules
    ├── generic/      # Capability-based actions
    │   ├── turn_on.yaml
    │   └── turn_off.yaml
    └── object_specific/  # Object-specific actions
        ├── flashlight/
        |   |   turn_on.yaml
        │   ├── replace_battery.yaml
        │   └── drain_battery.yaml
        └── kettle/
            ├── pour_water.yaml
            └── set_power.yaml
```

---

## 1️⃣ Qualitative Spaces - Value Domains

**Location**: `kb/spaces/common.yaml`

Spaces define the possible values for attributes and their order for comparisons.

```yaml
spaces:
  - id: binary_state           # ← Referenced by objects
    name: Binary State
    levels: ["off", "on"]       # ← Order matters for comparisons

  - id: battery_level
    name: Battery Level  
    levels: ["empty", "low", "medium", "high", "full"]  # ← Ordered progression

  - id: temperature_level
    name: Temperature Level
    levels: ["cold", "warm", "hot", "boiling"]
```

**Key Concepts:**
- `id`: Unique identifier used in object definitions
- `levels`: Ordered array - position determines comparison order
- Order enables `lt`, `lte`, `gt`, `gte` operators in conditions

### ⚡ Order-Aware Comparisons in Practice

The power of ordered spaces becomes clear when you use parametric actions:

```bash
# This works - pouring to 'full' level
uv run sim apply kettle pour_water -p to_level=full

# This fails - can't pour from 'mid' to 'low' (mid > low in the space)
uv run sim apply kettle pour_water -p to_level=low
```

**Expected Error:**
```
Status: rejected
Reason: Precondition failed: tank.level <= low (current: 'mid', target: 'low')
```

This demonstrates qualitative space ordering: `mid > low` in `["empty", "low", "mid", "full"]`.

 ---

## 2️⃣ Object Types - Structure Definition

**Location**: `kb/objects/*.yaml`

Objects define the structure and constraints of entities in your simulation.

```yaml
type: flashlight                # ← Referenced by actions

parts:                          # ← Component-based structure
  switch:
    attributes:
      position:
        space: binary_state     # ← References space ID
        default: "off"          # ← Must be valid level from space
        mutable: true           # ← Can be changed by actions

  bulb:
    attributes:
      state:
        space: binary_state
        default: "off"
        mutable: true
      brightness:
        space: brightness_level
        default: "none"
        mutable: true

  battery:
    attributes:
      level:
        space: battery_level
        default: "medium"
        mutable: true
      type:
        space: battery_types
        mutable: false          # ← Immutable - cannot be changed

# Business rules enforced after every action
constraints:
  - type: dependency
    condition:                  # ← Structured condition (same as actions)
      type: attribute_check
      target: bulb.state
      operator: equals
      value: on
    requires:                   # ← Structured condition
      type: attribute_check
      target: battery.level
      operator: not_equals
      value: empty
```

**Key Concepts:**
- **Parts**: Logical components (`switch`, `bulb`, `battery`)
- **Attributes**: Properties with specific value domains from spaces
- **Attribute Paths**: `part.attribute` format (e.g., `switch.position`)
- **Mutability**: `mutable: false` prevents changes (enforced by engine)
- **Constraints**: Business rules using the same condition language as actions

### 🔒 Constraint System in Action

Let's see how constraints enforce business rules. Try this sequence:

```bash
# First, drain the flashlight battery completely
uv run sim apply flashlight drain_battery

# Now try to force the bulb on (this violates our constraint)
uv run sim apply flashlight force_bulb_on
```

**Expected Output:**
```
Status: constraint_violated

⚠️  Constraint Violations (1):
  • Constraint violation: If bulb.state == on, then battery.level != empty

                Changes                
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Attribute  ┃ Before ┃ After ┃ Kind  ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ bulb.state │ off    │ on    │ value │
└────────────┴────────┴───────┴───────┘
```

**What this demonstrates:**
- Action completes but reports constraint violation
- Clean output with prominent violation warnings
- Same structured language used in constraints as actions

---

## 3️⃣ Actions - State Transitions

Actions define how objects can change state. There are two types:

### Capability-Based Actions (Generic)

**Location**: `kb/actions/generic/*.yaml`

Work on any object with the required capabilities:

```yaml
action: turn_on
object_type: generic            # ← Special marker for capability-based
required_capabilities: ["switchable"]  # ← Auto-detected from object structure

parameters:
  # No parameters needed for this action

preconditions:
  # Can only turn on if switch is currently off
  - type: attribute_check       # ← Unified condition language
    target: switch.position     # ← References object attribute path
    operator: equals            # ← Comparison operator
    value: "off"                # ← Expected value from space

effects:
  # Set switch to on position
  - type: set_attribute         # ← Effect type
    target: switch.position     # ← Attribute to modify
    value: "on"                 # ← New value (must be valid in space)
```

### 🎯 Generic Actions in Practice

The beauty of capability-based actions is **true polymorphism**. The same action works across different object types:

```bash
# Same action works on different objects with 'switchable' capability
uv run sim apply flashlight turn_on
uv run sim apply kettle turn_on
```

Both work because both objects have a `switch.position` attribute, making them "switchable".

**Try an error to see enhanced messages:**
```bash
# Turn on again (should fail - already on)
uv run sim apply flashlight turn_on
```

**Expected Error:**
```
Status: rejected
Reason: Precondition failed: switch.position == off (current: 'on', target: 'off')
```

Notice how the error message is crystal-clear: it shows exactly what condition failed and uses intuitive "current" vs "target" language.

### Object-Specific Actions

**Location**: `kb/actions/object_specific/<object>/*.yaml`

Work only on specific object types:

```yaml
action: replace_battery
object_type: flashlight         # ← Specific object type reference

parameters: {}                  # ← No parameters for this action

preconditions:
  # Can only replace battery when bulb is off (safety)
  - type: attribute_check
    target: bulb.state
    operator: equals
    value: off

effects:
  # Restore battery to full charge
  - type: set_attribute
    target: battery.level
    value: full
  # Stop any battery drain trend
  - type: set_trend
    target: battery.level
    direction: none
```

---

## 🔧 The Unified Condition Language

All conditions use the **same structured format** across preconditions and constraints.

> 🌟 **Key Innovation**: One language to learn, consistent across all components - no exceptions!

### Basic Attribute Checks

```yaml
# Equality check
- type: attribute_check
  target: switch.position       # part.attribute path
  operator: equals              # comparison operator
  value: "on"                   # expected value

# Inequality check  
- type: attribute_check
  target: battery.level
  operator: not_equals
  value: empty
```

### Ordered Comparisons

Uses the order defined in qualitative spaces:

```yaml
# Battery level must be above low
- type: attribute_check
  target: battery.level
  operator: gt                  # greater than
  value: low

# Temperature must be at least warm
- type: attribute_check
  target: heater.temperature
  operator: gte                 # greater than or equal
  value: warm
```

**Available Operators:**
- `equals`, `not_equals` - Equality/inequality
- `lt`, `lte`, `gt`, `gte` - Ordered comparisons using space levels

### Parameter Validation

For actions with user input:

```yaml
# Check parameter is valid
- type: parameter_valid
  parameter: to_level           # parameter name
  valid_values: ["low", "mid", "full"]

# Check parameter has specific value
- type: parameter_equals
  parameter: mode
  value: "safe"
```

### Logical Composition

Combine conditions with boolean logic:

```yaml
# Multiple conditions must all be true
- type: and
  conditions:
    - type: attribute_check
      target: switch.position
      operator: equals
      value: off
    - type: attribute_check
      target: battery.level
      operator: not_equals
      value: empty

# At least one condition must be true
- type: or
  conditions:
    - type: attribute_check
      target: power.source
      operator: equals
      value: battery
    - type: attribute_check
      target: power.source
      operator: equals
      value: external

# Condition must be false
- type: not
  conditions:
    - type: attribute_check
      target: safety.locked
      operator: equals
      value: true
```

### 🎮 Interactive YAML Editing Demo

Let's see the unified language in action by adding complex logic to an existing action.

**Current State**: Open `kb/actions/object_specific/kettle/pour_water.yaml` and try adding this safety precondition:

```yaml
preconditions:
  - type: attribute_check
    target: control.power
    operator: equals
    value: off
  # NEW: Complex safety condition using OR logic
  - type: or
    conditions:
      - type: attribute_check
        target: heater.temperature
        operator: equals
        value: cold
      - type: and
        conditions:
          - type: attribute_check
            target: heater.temperature
            operator: equals
            value: warm
          - type: attribute_check
            target: control.power
            operator: equals
            value: off
```

**Test the Complex Logic:**
```bash
uv run sim apply kettle pour_water -p to_level=full
```

This demonstrates **rich logical composition** using the unified structured language - the same syntax works everywhere.

### Implication Logic

"If condition A, then condition B must also be true":

```yaml
# If turning on, battery must not be empty
- type: implication
  if:
    type: parameter_equals
    parameter: to
    value: "on"
  then:
    type: attribute_check
    target: battery.level
    operator: not_equals
    value: empty
```

---

## ⚡ Effects - What Changes

Effects modify object state when actions are applied.

### Set Attribute Value

```yaml
# Set to fixed value
- type: set_attribute
  target: switch.position
  value: "on"

# Set using parameter (see Parameters section)
- type: set_attribute
  target: tank.level
  value:
    type: parameter_ref
    name: to_level
```

### Set Trend Direction

Indicates the direction of change over time:

```yaml
# Battery is draining
- type: set_trend
  target: battery.level
  direction: down

# Temperature is rising
- type: set_trend
  target: heater.temperature
  direction: up

# No change in level
- type: set_trend
  target: tank.level
  direction: none
```

### Conditional Effects

Apply different effects based on conditions:

```yaml
- type: conditional
  condition:
    type: attribute_check
    target: switch.position
    operator: equals
    value: on
  then:
    # If switch is on, bulb lights up
    - type: set_attribute
      target: bulb.state
      value: "on"
    - type: set_trend
      target: battery.level
      direction: down
  else:
    # If switch is off, bulb goes dark
    - type: set_attribute
      target: bulb.state
      value: "off"
    - type: set_trend
      target: battery.level
      direction: none
```

---

## 📝 Parameters - User Input

Actions can accept parameters for dynamic behavior:

```yaml
action: pour_water
object_type: kettle

parameters:
  to_level:
    type: choice                # Parameter type
    choices: [low, mid, full]   # Valid options
    required: true              # Must be provided

preconditions:
  # Power must be off before pouring
  - type: attribute_check
    target: control.power
    operator: equals
    value: off

effects:
  # Set water level to user's choice
  - type: set_attribute
    target: tank.level
    value:
      type: parameter_ref       # Reference to parameter
      name: to_level           # Parameter name
```

**Usage**: `uv run sim apply kettle pour_water -p to_level=full`

### 🎯 Parameters with Validation

Parameters enable dynamic behavior with built-in validation:

```bash
# Valid parameter - works fine
uv run sim apply kettle pour_water -p to_level=full

# Invalid parameter - clear error message
uv run sim apply kettle pour_water -p to_level=invalid
```

**Expected Error:**
```
Status: rejected  
Reason: Parameter 'to_level' must be one of: [low, mid, full] (provided: 'invalid')
```

This shows how parameter validation integrates seamlessly with the condition system.

---

## 🔒 Constraints - Business Rules

Constraints enforce business rules and are checked after every action:

```yaml
constraints:
  # Dependency: "If A then B must also be true"
  - type: dependency
    condition:                  # Uses same language as preconditions
      type: attribute_check
      target: bulb.state
      operator: equals
      value: on
    requires:
      type: attribute_check
      target: battery.level
      operator: not_equals
      value: empty
```

**When Violated**: Action completes but returns `status: "constraint_violated"` with human-readable violation messages.

### 📝 Adding New Constraints Live

You can add new constraints to objects in real-time. Try adding this safety constraint to `kb/objects/flashlight.yaml`:

```yaml
constraints:
  - type: dependency
    condition:
      type: attribute_check
      target: bulb.state
      operator: equals
      value: on
    requires:
      type: attribute_check
      target: battery.level
      operator: not_equals
      value: empty
  # NEW: Safety constraint - switch must be on if bulb is on
  - type: dependency
    condition:
      type: attribute_check
      target: bulb.state
      operator: equals
      value: on
    requires:
      type: attribute_check
      target: switch.position
      operator: equals
      value: on
```

**Test the New Constraint:**
```bash
# Turn flashlight on first
uv run sim apply flashlight replace_battery  # Restore battery
uv run sim apply flashlight turn_on

# Now try to replace battery while on (should violate new constraint)
uv run sim apply flashlight replace_battery
```

This shows how constraints use the **same language as actions** - complete consistency across the system.

---

## 🚀 Engine Execution Flow

When you run an action, the engine follows this process:

1. **Parameter Validation**: Check required parameters and valid choices
2. **Context Building**: Create evaluation context with object instance
3. **Precondition Checking**: All preconditions must pass or action is rejected
4. **Effect Application**: Apply effects in order, validating against spaces
5. **Constraint Enforcement**: Check all constraints on final state
6. **Result Generation**: Return detailed before/after state with changes

---

## 💻 CLI Usage

All commands use: `uv run sim <command>`

### 🎮 Clean vs Full Output Modes

By default, the CLI shows a **clean, presentation-friendly output**:

```bash
# Clean summary (default) - perfect for presentations
uv run sim apply flashlight turn_off
```

**Clean Output:**
```
Status: ok
                  Changes                   
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Attribute       ┃ Before ┃ After ┃ Kind  ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ switch.position │ off    │ on    │ value │
└─────────────────┴────────┴───────┴───────┘
```

```bash
# Full details when debugging
uv run sim apply flashlight turn_off --full
```

**When to use `--full`:**
- Debugging complex issues
- Understanding complete object state  
- API integration testing

**Error Example:**
```
Status: rejected
Reason: Precondition failed: tank.level < full (current: 'full', target: 'full')
```

**Constraint Violation:**
```
Status: constraint_violated

⚠️  Constraint Violations (1):
  • Constraint violation: If bulb.state == on, then battery.level != empty

                Changes                
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Attribute  ┃ Before ┃ After ┃ Kind  ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ bulb.state │ off    │ on    │ value │
└────────────┴────────┴───────┴───────┘
```

### Validate Knowledge Base
```bash
uv run sim validate
```
Checks that all YAML files are valid and references exist.

### Inspect Objects
```bash
# Show object current state (includes current values, trends ↑↓→, confidence)
uv run sim show object flashlight

# Show full object details (verbose JSON output)
uv run sim show object flashlight --full

# Show capabilities (for generic actions)
uv run sim show capabilities flashlight
```

### Apply Actions
```bash
# Simple action (no parameters) - clean output by default
uv run sim apply flashlight turn_on

# Action with parameters
uv run sim apply kettle pour_water -p to_level=full

# Multiple parameters
uv run sim apply device configure -p mode=safe -p level=high

# Show full object states (verbose output)
uv run sim apply flashlight turn_on --full

# Simple action (no parameters)
```

### CLI Output Modes

**Show Command:**
- **Default**: Default state table with values, trends (↑↓→), confidence, mutability
- **`--full`**: Complete JSON output with full object instance details

**Apply Command:**
- **Default**: Clean summary with status, changes table, and error details
- **`--full`**: Complete JSON output with full object states

### Exit Codes
- `0`: Success
- `1`: Validation or execution errors (including constraint violations)
- `2`: Bad usage (malformed parameters)

---

## 🔧 Programmatic Usage

```python
from simulator.core.registries import RegistryManager
from simulator.io.loaders.yaml_loader import load_spaces
from simulator.io.loaders.object_loader import load_object_types, instantiate_default
from simulator.io.loaders.action_loader import load_actions
from simulator.core.engine import TransitionEngine

# Setup
rm = RegistryManager()
rm.register_defaults()
load_spaces("kb/spaces", rm)
load_object_types("kb/objects", rm)
load_actions("kb/actions", rm)
rm.detect_and_register_capabilities()

# Create object instance
obj = rm.objects.get("flashlight")
inst = instantiate_default(obj, rm)

# Apply action
action = rm.actions.get("capability:turn_on")
engine = TransitionEngine(rm)
result = engine.apply_action(inst, action, {})

print(f"Status: {result.status}")
print(f"Changes: {result.changes}")
```

---

## ✅ Validation & Error Handling

### Attribute Validation
- All attribute writes are validated against qualitative spaces
- Invalid values are rejected with clear error messages
- Attribute paths are validated; errors list available parts/attributes

### Constraint Violations
- Constraints are evaluated after effects are applied
- Violations include human-readable descriptions
- Actions complete but return violation status

### Enhanced Error Messages
- **Crystal-clear failures**: Shows exactly what condition failed and why
- **Resolved parameters**: Parameter references show actual values, not variable names
- **Current vs Target**: Error messages use intuitive "current" and "target" instead of "actual" and "expected"

**Example Error Messages:**
```
Status: rejected
Reason: Precondition failed: tank.level < full (current: 'full', target: 'full')
```

### Parameter Validation
- Required parameters must be provided
- Choice parameters must use valid options
- Type mismatches are caught with helpful messages

---

## 🧠 Language Unification Benefits

### Before vs After Comparison

**Old System Problems** (now fixed):
- `attribute_equals` vs `attribute_check` inconsistency ❌
- String expressions vs structured conditions ❌  
- Verbose JSON output overwhelming users ❌
- Generic error messages ❌

**New Unified System** ✅:
- **Single condition language** everywhere
- **6 comparison operators** with qualitative space ordering
- **Clean, focused output** with `--full` option
- **Crystal-clear error messages** with actual/expected values
- **Same syntax** in preconditions, effects, and constraints

## 🚫 What's NOT Supported

- **Legacy `attribute_equals`**: Use `attribute_check` with `operator: equals`
- **String expressions**: All conditions must be structured YAML
- **Arithmetic operations**: This is a qualitative simulator
- **Complex expressions**: Keep conditions simple and composable

---

## 📚 Complete Examples

### Simple Binary Switch
```yaml
# Object
type: lamp
parts:
  switch:
    attributes:
      position:
        space: binary_state
        default: "off"
        mutable: true

# Action  
action: toggle_lamp
object_type: lamp
preconditions:
  - type: attribute_check
    target: switch.position
    operator: equals
    value: off
effects:
  - type: set_attribute
    target: switch.position
    value: "on"
```

### Parametric Action with Validation
```yaml
action: set_temperature
object_type: heater
parameters:
  target_temp:
    type: choice
    choices: ["cold", "warm", "hot"]
    required: true
preconditions:
  - type: parameter_valid
    parameter: target_temp
    valid_values: ["cold", "warm", "hot"]
  - type: attribute_check
    target: power.state
    operator: equals
    value: on
effects:
  - type: set_attribute
    target: heating_element.temperature
    value:
      type: parameter_ref
      name: target_temp
```

### Complex Constraint with Logic
```yaml
constraints:
  - type: dependency
    condition:
      type: and
      conditions:
        - type: attribute_check
          target: motor.running
          operator: equals
          value: true
        - type: attribute_check
          target: fluid.level
          operator: gt
          value: empty
    requires:
      type: attribute_check
      target: safety.enabled
      operator: equals
      value: true
```

---

## 🎯 Best Practices

1. **Start Simple**: Begin with binary states and basic actions
2. **Use Meaningful Names**: Make attribute and action names self-explanatory
3. **Order Matters**: Arrange space levels in logical progression
4. **Test Constraints**: Use actions that should violate constraints to verify they work
5. **Validate Early**: Run `uv run sim validate` frequently during development
6. **Document Intent**: Use YAML comments to explain complex logic
7. **Clean Output**: Default output is presentation-friendly; use `--full` only when debugging

## 🚀 Quick Command Reference

```bash
# System check
uv run sim validate

# Exploration
uv run sim show object flashlight
uv run sim show capabilities flashlight

# Basic actions
uv run sim apply flashlight turn_on
uv run sim apply kettle pour_water -p to_level=full

# Error showcase
uv run sim apply flashlight turn_on  # Precondition failure

# Constraint violation demo
uv run sim apply flashlight drain_battery
uv run sim apply flashlight force_bulb_on

# Output modes
uv run sim apply flashlight turn_off           # Clean
uv run sim apply flashlight turn_off --full    # Detailed
```

---

## 💡 Key Talking Points for Presentations

### 🌟 **Unified Language**
- "Same structured conditions everywhere - no exceptions!"
- "One language to learn, consistent across all components"

### ⚡ **Order-Aware Comparisons**  
- "Qualitative reasoning beyond just equality"
- "Battery level > low makes sense in our domain"

### 🔒 **Constraint System**
- "Business rules use the same language as actions"
- "Violations are descriptive, not just error codes"

### 🎯 **User Experience**
- "Clean output by default, details when you need them"
- "Error messages tell you exactly what went wrong"

### 🏗️ **Capability-Driven**
- "Actions work on what objects can do, not what they are"
- "True polymorphism in qualitative simulations"

---

This unified language provides a consistent, powerful way to model qualitative systems. Everything uses the same structured conditions - no exceptions, no legacy syntax, just clear, composable rules that work the same everywhere.

**This is a production-ready qualitative simulation system** with a beautiful, unified architecture that's both powerful and learnable!