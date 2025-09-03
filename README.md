# Mental Models Simulator — Ground-Truth Benchmark Engine

A deterministic, qualitative simulator for everyday objects that produces canonical, labeled state transitions for benchmarking AI mental models.

## 🎯 Purpose

Build a ground-truth simulator (NOT LLM-facing) that defines canonical behavior for everyday objects. External AI models will be evaluated against the datasets we generate.

## ✅ Current System Status (Phase 2 Complete - Unified Language)

### **Architecture with Unified Language**

The simulator features a robust, validated system with:

- **Unified Condition Language**: Single structured format for preconditions, effects, and constraints
- **Clean Default State Display**: CLI shows default values from YAML definitions, not runtime state
- **Safe State Mutations**: All attribute writes validated against qualitative spaces  
- **Constraint Enforcement**: Business rules using same structured conditions as actions
- **Capability-Based Actions**: Generic actions work across compatible object types
- **Order-Aware Comparisons**: Support for lt, lte, gt, gte operators using qualitative space ordering
- **Comprehensive Validation**: Cross-registry validation catches broken references
- **Rich Error Messages**: Clear diagnostics with available options listed
- **Immutable Snapshots**: State diffing and change tracking utilities

### **Core Components**

- **✅ Knowledge Base**: YAML-based authoring with unified structured conditions
- **✅ Object Model**: Parts-based architecture with structured constraint definitions
- **✅ Action Engine**: Unified condition language with 6 comparison operators (equals, not_equals, lt, lte, gt, gte)
- **✅ Capability System**: Automatic detection and generic action compatibility  
- **✅ Constraint Engine**: Structured conditions matching action preconditions exactly
- **✅ State Tracking**: Full before/after states with detailed change diffs
- **✅ Utilities**: Object builders, state snapshots, logging helpers

## Quick Start

```bash
# Install dependencies
uv sync

# Validate knowledge base with unified language
uv run sim validate

# Show object capabilities
uv run sim show capabilities flashlight

# Apply actions with structured condition validation
uv run sim apply flashlight turn_on

# Apply parametric actions
uv run sim apply kettle pour_water -p to_level=full
```



## 🏗️ Architecture

```
src/simulator/
├── core/
│   ├── capabilities/     # Capability detection & registry
│   ├── constraints/      # Constraint engine & validation
│   ├── objects/          # ObjectType, ObjectInstance, AttributeTarget
│   ├── actions/          # Action conditions, effects, parameters  
│   ├── registries/       # In-memory storage + cross-validation
│   └── engine/           # Action application + state transitions
├── io/loaders/           # YAML → validated objects
└── cli/                  # CLI commands

kb/                       # Knowledge base (YAML files)
├── spaces/               # Qualitative spaces (binary_state, battery_level, etc.)
├── objects/              # Object definitions (flashlight.yaml, kettle.yaml, etc.)
└── actions/
    └── generic/          # Capability-based actions (turn_on.yaml, turn_off.yaml)
```

## 🔬 Design Principles

- **Unified Language**: Single structured condition format across all components
- **Capability-Based**: Actions work on object capabilities, not specific types  
- **Constraint-Driven**: Business rules enforced automatically using structured conditions
- **Order-Aware**: Qualitative space ordering enables lt/gt comparisons
- **Deterministic**: Same input → same output, full state tracking
- **Safe DSL**: No Python eval, only structured YAML conditions
- **YAML Authoring**: Human-readable, version-controlled knowledge base

## 📊 Current System Stats

- **Object Types**: 3 (flashlight, kettle, bottle)
- **Capabilities**: 6 (switchable, illuminating, battery_powered, fillable, heatable, water_container)
- **Generic Actions**: 2 (turn_on, turn_off) using unified structured conditions
- **Object-Specific Actions**: 5 (replace_battery, pour_water, set_power, drain_battery, force_bulb_on)
- **Qualitative Spaces**: 8 with 2-7 levels each supporting order-aware comparisons
- **Condition Operators**: 6 (equals, not_equals, lt, lte, gt, gte) 
- **Constraint Types**: 1 (dependency constraints using structured conditions)
- **CLI Commands**: 3 (validate, show, apply) with unified syntax

## 💡 Key Features

### **Capability Detection**
Objects automatically get capabilities based on their structure:
- `flashlight`: switchable, illuminating, battery_powered
- `kettle`: switchable, heatable, water_container  
- `bottle`: fillable

### **Smart Action Resolution**
The system finds compatible actions automatically:
- `turn_on` works on flashlight, kettle (both have "switchable")
- `replace_battery` only works on battery_powered objects
- `pour_water` only works on water_container objects

### **Unified Constraint Language**
Business rules use the same structured conditions as actions:
- Flashlight constraint: "If bulb.state equals on, then battery.level not_equals empty"
- Structured format enables complex logical composition (and, or, not, implication)
- Actions that would violate constraints are caught and reported with clear messages

## 📚 Documentation

- **[Complete Usage Guide](usage_instructions.md)**: Comprehensive guide with unified YAML language, interactive examples, live demos, structured conditions, CLI usage, and programmatic API. Works as both reference documentation and presentation material.
