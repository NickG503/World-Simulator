#!/bin/bash
# Run all examples from EXAMPLES.md and generate visualizations
# Usage: ./scripts/run_examples.sh
#
# Outputs are organized into categorized folders:
# - outputs/1_basic/           - Simple linear simulations
# - outputs/2_initial_values/  - Simulations with initial values set
# - outputs/3_branching/       - Simulations with unknown values (branching)
# - outputs/4_in_operator/     - Advanced branching with IN operator
# - outputs/5_intersection/    - Same attribute branching (intersection logic)
# - outputs/6_multi_level/     - Multi-level branching (complex)
# - outputs/7_dag_merging/     - DAG state deduplication (node merging)
# - outputs/8_comparison_ops/  - Comparison operators (>=, >, <=, <) - Coffee Machine
# - outputs/9_compound_and/    - AND compound conditions - Coffee Machine
# - outputs/10_compound_or/    - OR compound conditions - Slot Machine
# - outputs/11_compound_seq/   - Multi-action sequences with compound conditions
# - outputs/12_recursive_demorgan/ - Nested/recursive De Morgan's law tests

set -e

echo "=========================================="
echo "World Simulator - Running All Examples"
echo "=========================================="

# Create output directories
mkdir -p outputs/1_basic
mkdir -p outputs/2_initial_values
mkdir -p outputs/3_branching
mkdir -p outputs/4_in_operator
mkdir -p outputs/5_intersection
mkdir -p outputs/6_multi_level
mkdir -p outputs/7_dag_merging
mkdir -p outputs/8_comparison_ops
mkdir -p outputs/9_compound_and
mkdir -p outputs/10_compound_or
mkdir -p outputs/11_compound_seq
mkdir -p outputs/12_recursive_demorgan

# Keep the default output folder for the simulator to use
mkdir -p outputs/histories
mkdir -p outputs/visualizations

# Clean previous outputs
rm -f outputs/histories/*.yaml
rm -f outputs/visualizations/*.html

# Helper function to run simulation and move to category folder
run_sim() {
    local category=$1
    local name=$2
    shift 2

    echo "  Running: $name"
    uv run sim simulate "$@" --name "$name"

    # Move the generated files to the category folder
    if [ -f "outputs/histories/${name}.yaml" ]; then
        mv "outputs/histories/${name}.yaml" "outputs/${category}/${name}.yaml"
    fi
}

# Helper function to generate visualization for a category
viz_category() {
    local category=$1
    echo ""
    echo "  Visualizing category: $category"

    for history in outputs/${category}/*.yaml; do
        if [ -f "$history" ]; then
            name=$(basename "$history" .yaml)
            uv run sim visualize "$history" -o "outputs/${category}/${name}.html" --no-open
        fi
    done
}

echo ""
echo "0. VALIDATION"
echo "=========================================="

echo "Validating knowledge base..."
uv run sim validate

echo ""
echo "1. BASIC LINEAR SIMULATIONS"
echo "=========================================="

CATEGORY="1_basic"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" flashlight_basic --obj flashlight --actions turn_on turn_off
run_sim "$CATEGORY" flashlight_multi --obj flashlight --actions turn_on turn_off turn_on

viz_category "$CATEGORY"

echo ""
echo "2. SETTING INITIAL VALUES"
echo "=========================================="

CATEGORY="2_initial_values"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" flashlight_low --obj flashlight --set battery.level=low --actions turn_on turn_off
run_sim "$CATEGORY" flashlight_full --obj flashlight --set battery.level=full --actions turn_on turn_off
run_sim "$CATEGORY" flashlight_empty --obj flashlight --set battery.level=empty --actions turn_on

viz_category "$CATEGORY"

echo ""
echo "3. BRANCHING ON UNKNOWN VALUES"
echo "=========================================="

CATEGORY="3_branching"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" flashlight_unknown --obj flashlight --set battery.level=unknown --actions turn_on
run_sim "$CATEGORY" flashlight_unknown_cycle --obj flashlight --set battery.level=unknown --actions turn_on turn_off

viz_category "$CATEGORY"

echo ""
echo "4. ADVANCED BRANCHING WITH IN OPERATOR"
echo "=========================================="

CATEGORY="4_in_operator"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" dice_known --obj dice --set cube.face=3 cube.color=green --actions check_win
run_sim "$CATEGORY" dice_branching --obj dice --set cube.face=unknown cube.color=unknown --actions check_win

# Slot machine IN operator: symbol in {seven, bar}
echo ""
echo "  Slot machine IN operator examples:"
run_sim "$CATEGORY" slot_in_operator --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown --actions check_high_symbols

viz_category "$CATEGORY"

echo ""
echo "5. SAME ATTRIBUTE BRANCHING (INTERSECTION LOGIC)"
echo "=========================================="

CATEGORY="5_intersection"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" dice_same_known --obj dice_same_attr --set cube.face=3 --actions check_win
run_sim "$CATEGORY" dice_same_branching --obj dice_same_attr --set cube.face=unknown --actions check_win

viz_category "$CATEGORY"

echo ""
echo "6. MULTI-LEVEL BRANCHING (COMPLEX)"
echo "=========================================="

CATEGORY="6_multi_level"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" flashlight_double_branch --obj flashlight --set battery.level=unknown --actions turn_on turn_on
run_sim "$CATEGORY" flashlight_cycle_branch --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on

viz_category "$CATEGORY"

echo ""
echo "7. DAG STATE DEDUPLICATION (NODE MERGING)"
echo "=========================================="

CATEGORY="7_dag_merging"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

run_sim "$CATEGORY" flashlight_4cycle --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on turn_off
run_sim "$CATEGORY" dice_multiround --obj dice_same_attr --set cube.face=unknown --actions check_win reset check_win
run_sim "$CATEGORY" dice_5actions --obj dice_same_attr --set cube.face=unknown --actions check_win reset check_win reset check_win
run_sim "$CATEGORY" dice_double_merge --obj dice_double_merge --set cube.face=unknown cube.color=unknown --actions roll_face reset_face roll_color reset_color

viz_category "$CATEGORY"

echo ""
echo "8. COMPARISON OPERATORS - Coffee Machine (>=, >, <=, <)"
echo "=========================================="

CATEGORY="8_comparison_ops"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

echo ""
echo "  Coffee machine comparison operator examples:"

# heater.temperature < hot (expands to {cold, warm})
run_sim "$CATEGORY" coffee_heat_lt --obj coffee_machine --set heater.temperature=unknown --actions heat_up

# heater.temperature > cold (expands to {warm, hot})
run_sim "$CATEGORY" coffee_cool_gt --obj coffee_machine --set heater.temperature=unknown --actions cool_down

viz_category "$CATEGORY"

echo ""
echo "9. AND COMPOUND CONDITIONS - Coffee Machine (De Morgan's Law)"
echo "=========================================="

CATEGORY="9_compound_and"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

echo ""
echo "  Coffee machine AND precondition tests:"

# AND precondition: water >= low AND beans >= low AND temp == hot
# With one unknown
run_sim "$CATEGORY" coffee_brew_one_unknown --obj coffee_machine --set water_tank.level=medium bean_hopper.amount=unknown heater.temperature=hot --actions brew_espresso

# With two unknowns (De Morgan: 1 success + 2 fail)
run_sim "$CATEGORY" coffee_brew_two_unknown --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=hot --actions brew_espresso

echo ""
echo "  Coffee machine AND postcondition tests (De Morgan ELSE):"

# AND in postcondition: if (water >= low AND temp == hot) then ready = on
run_sim "$CATEGORY" coffee_check_ready --obj coffee_machine --set water_tank.level=unknown heater.temperature=unknown --actions check_ready

viz_category "$CATEGORY"

echo ""
echo "10. OR COMPOUND CONDITIONS - Slot Machine (De Morgan's Law)"
echo "=========================================="

CATEGORY="10_compound_or"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

echo ""
echo "  Slot machine OR precondition tests (De Morgan FAIL):"

# OR precondition: reel1 == seven OR reel2 == seven OR reel3 == seven
# With two unknowns: creates multiple success branches + 1 fail (De Morgan)
run_sim "$CATEGORY" slot_any_seven_2unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=bar --actions check_any_seven

# With all three unknowns
run_sim "$CATEGORY" slot_any_seven_3unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven

echo ""
echo "  Slot machine OR postcondition tests (De Morgan ELSE):"

# OR in postcondition: if (reel1 == seven OR reel2 == bar) then prize = small
run_sim "$CATEGORY" slot_award_prize --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown --actions award_prize

# IN operator in postcondition: symbol in {cherry, lemon}
run_sim "$CATEGORY" slot_check_fruit --obj slot_machine --set reel1.symbol=unknown --actions check_fruit

viz_category "$CATEGORY"

echo ""
echo "11. MULTI-ACTION WITH COMPOUND CONDITIONS"
echo "=========================================="

CATEGORY="11_compound_seq"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

echo ""
echo "  Coffee machine multi-action sequence:"

# Sequence: heat_up -> brew_espresso (with compound preconditions)
run_sim "$CATEGORY" coffee_heat_then_brew --obj coffee_machine --set water_tank.level=medium bean_hopper.amount=medium heater.temperature=unknown --actions heat_up brew_espresso

# Full coffee cycle: refill -> heat_up -> brew
run_sim "$CATEGORY" coffee_full_cycle --obj coffee_machine --set heater.temperature=cold water_tank.level=low --actions refill_water heat_up brew_espresso

echo ""
echo "  Slot machine multi-action sequence:"

# Check for sevens then reset (starting with unknown reels)
run_sim "$CATEGORY" slot_check_reset --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven reset

viz_category "$CATEGORY"

echo ""
echo "12. RECURSIVE DE MORGAN - Nested Compound Conditions"
echo "=========================================="

CATEGORY="12_recursive_demorgan"
rm -f outputs/${CATEGORY}/*.yaml outputs/${CATEGORY}/*.html

echo ""
echo "  Nested AND inside OR: (A AND B) OR C"
echo "  De Morgan: NOT((A AND B) OR C) = (NOT A OR NOT B) AND NOT C"

# nested_compound: (reel1 == seven AND reel2 == seven) OR reel3 == seven
# Expect: 3 success branches + 1 fail branch with nested structure
run_sim "$CATEGORY" nested_and_in_or_3unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions nested_compound

# With one known value that satisfies - reduces branching
run_sim "$CATEGORY" nested_and_in_or_1known --obj slot_machine --set reel1.symbol=seven reel2.symbol=unknown reel3.symbol=unknown --actions nested_compound

# With one known value that doesn't satisfy the inner AND
run_sim "$CATEGORY" nested_and_in_or_1known_fail --obj slot_machine --set reel1.symbol=cherry reel2.symbol=unknown reel3.symbol=unknown --actions nested_compound

echo ""
echo "  Simple AND De Morgan: A AND B AND C"
echo "  De Morgan: NOT(A AND B AND C) = NOT A OR NOT B OR NOT C"

# 3-way AND with all unknowns - should create 3 fail branches
run_sim "$CATEGORY" and_3unknown --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=unknown --actions brew_espresso

# 3-way AND with 2 unknowns - should create 2 fail branches
run_sim "$CATEGORY" and_2unknown --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=hot --actions brew_espresso

echo ""
echo "  Simple OR De Morgan: A OR B OR C"
echo "  De Morgan: NOT(A OR B OR C) = NOT A AND NOT B AND NOT C"

# 3-way OR with all unknowns - should create 3 success + 1 fail (compound AND)
run_sim "$CATEGORY" or_3unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven

# 3-way OR with 1 known satisfying - fewer branches
run_sim "$CATEGORY" or_1known_pass --obj slot_machine --set reel1.symbol=seven reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven

# 3-way OR with 1 known non-satisfying
run_sim "$CATEGORY" or_1known_fail --obj slot_machine --set reel1.symbol=cherry reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven

echo ""
echo "  Postcondition De Morgan tests:"

# AND postcondition with unknowns (creates ELSE branches via De Morgan)
run_sim "$CATEGORY" postcond_and_demorgan --obj coffee_machine --set water_tank.level=unknown heater.temperature=unknown --actions check_ready

# OR postcondition with unknowns
run_sim "$CATEGORY" postcond_or_demorgan --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown --actions award_prize

# Complex postcondition: if (AND) elif (OR) else
run_sim "$CATEGORY" postcond_mixed_if_elif_else --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown --actions complex_postcondition

# Flat if/elif/else: nested but single-attribute conditions
run_sim "$CATEGORY" postcond_flat_if_elif --obj coffee_machine --set water_tank.level=unknown heater.temperature=unknown --actions check_status

echo ""
echo "  Complex multi-action with recursive De Morgan:"

# Multi-action: each action has compound preconditions
run_sim "$CATEGORY" multi_action_recursive --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=cold --actions heat_up brew_espresso

# Nested compound through multiple actions
run_sim "$CATEGORY" slot_nested_sequence --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions nested_compound check_any_seven

echo ""
echo "  Cartesian product: Precond OR × Postcond OR on UNRELATED attributes:"

# Precond: (face=6 OR color=red) × Postcond: (size=large OR weight=heavy) ELSE
# Creates 2 precond success × 3 postcond branches = 6 success + 1 fail = 7 branches
run_sim "$CATEGORY" cartesian_product --obj dice_cartesian --set cube.face=unknown cube.color=unknown cube.size=unknown cube.weight=unknown --actions check_cartesian

viz_category "$CATEGORY"

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""
echo "Categorized outputs:"
for category_dir in outputs/*/; do
    category=$(basename "$category_dir")
    if [[ "$category" != "histories" && "$category" != "visualizations" ]]; then
        yaml_count=$(ls -1 ${category_dir}*.yaml 2>/dev/null | wc -l | tr -d ' ')
        html_count=$(ls -1 ${category_dir}*.html 2>/dev/null | wc -l | tr -d ' ')
        echo "  ${category}: ${yaml_count} simulations, ${html_count} visualizations"
    fi
done

echo ""
echo "=========================================="
echo "All examples completed successfully!"
echo "=========================================="
