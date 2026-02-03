#!/bin/bash
# Run essential examples from World Simulator and generate visualizations
# Usage: ./scripts/run_examples.sh
#
# All outputs go to: outputs/examples/

set -e

echo "=========================================="
echo "World Simulator - Running Examples"
echo "=========================================="

# Create single output directory
OUTPUT_DIR="outputs/examples"
mkdir -p "$OUTPUT_DIR"

# Keep the default output folder for the simulator to use
mkdir -p outputs/histories
mkdir -p outputs/visualizations

# Clean previous outputs
rm -f outputs/histories/*.yaml
rm -f outputs/visualizations/*.html
rm -f "$OUTPUT_DIR"/*.yaml "$OUTPUT_DIR"/*.html

# Helper function to run simulation and move to output folder
run_sim() {
    local name=$1
    shift

    echo "  Running: $name"
    uv run sim simulate "$@" --name "$name"

    # Move the generated file to the output folder
    if [ -f "outputs/histories/${name}.yaml" ]; then
        mv "outputs/histories/${name}.yaml" "${OUTPUT_DIR}/${name}.yaml"
    fi
}

# Helper function to generate visualization for all yaml files
viz_all() {
    echo ""
    echo "Generating visualizations..."

    for history in ${OUTPUT_DIR}/*.yaml; do
        if [ -f "$history" ]; then
            name=$(basename "$history" .yaml)
            echo "  Visualizing: $name"
            uv run sim visualize "$history" -o "${OUTPUT_DIR}/${name}.html" --no-open
        fi
    done
}

echo ""
echo "0. VALIDATION"
echo "=========================================="

echo "Validating knowledge base..."
uv run sim validate

echo ""
echo "1. BASIC SIMULATIONS"
echo "=========================================="

run_sim flashlight_basic --obj flashlight --actions turn_on turn_off
run_sim flashlight_multi --obj flashlight --actions turn_on turn_off turn_on

echo ""
echo "2. INITIAL VALUES & EDGE CASES"
echo "=========================================="

run_sim flashlight_empty --obj flashlight --set battery.level=empty --actions turn_on

echo ""
echo "3. BRANCHING (UNKNOWN VALUES)"
echo "=========================================="

run_sim flashlight_unknown --obj flashlight --set battery.level=unknown --actions turn_on
run_sim dice_branching --obj dice --set cube.face=unknown cube.color=unknown --actions check_win

echo ""
echo "4. MULTI-LEVEL BRANCHING"
echo "=========================================="

run_sim flashlight_cycle_branch --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on

echo ""
echo "5. DAG STATE MERGING"
echo "=========================================="

run_sim flashlight_4cycle --obj flashlight --set battery.level=unknown --actions turn_on turn_off turn_on turn_off
run_sim dice_multiround --obj dice_same_attr --set cube.face=unknown --actions check_win reset check_win

echo ""
echo "6. COMPARISON OPERATORS"
echo "=========================================="

run_sim coffee_heat_lt --obj coffee_machine --set heater.temperature=unknown --actions heat_up

echo ""
echo "7. COMPOUND CONDITIONS (AND/OR)"
echo "=========================================="

run_sim coffee_brew_two_unknown --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=hot --actions brew_espresso
run_sim slot_any_seven_3unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions check_any_seven

echo ""
echo "8. MULTI-ACTION WITH COMPOUND CONDITIONS"
echo "=========================================="

run_sim coffee_full_cycle --obj coffee_machine --set heater.temperature=cold water_tank.level=low --actions refill_water heat_up brew_espresso

echo ""
echo "9. NESTED COMPOUND CONDITIONS (De Morgan)"
echo "=========================================="

run_sim nested_and_in_or_3unknown --obj slot_machine --set reel1.symbol=unknown reel2.symbol=unknown reel3.symbol=unknown --actions nested_compound
run_sim and_3unknown --obj coffee_machine --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=unknown --actions brew_espresso

echo ""
echo "10. CARTESIAN PRODUCT BRANCHING"
echo "=========================================="

run_sim full_cartesian_4unknown --obj dice_cartesian --set cube.face=unknown cube.color=unknown cube.size=unknown cube.weight=unknown --actions check_cartesian

echo ""
echo "11. SOLVER PATTERN"
echo "=========================================="

run_sim tv_on_off --obj tv --actions turn_on turn_off
run_sim kettle_workflow --obj kettle --set tank.level=full --actions turn_on turn_off

echo ""
echo "12. TIME CONSTRAINTS (TRENDS)"
echo "=========================================="

# Kettle with pour action - demonstrates water level trending down
run_sim kettle_pour --obj kettle --set tank.level=full --actions turn_on pour

# Coffee machine heat_up with full workflow showing time constraints
run_sim coffee_heat_time --obj coffee_machine --set heater.temperature=cold --actions heat_up

# Flashlight shake - demonstrates persistent trend across passive action
run_sim flashlight_shake --obj flashlight --set battery.level=unknown --actions turn_on shake

# Generate all visualizations at the end
viz_all

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""

yaml_count=$(ls -1 ${OUTPUT_DIR}/*.yaml 2>/dev/null | wc -l | tr -d ' ')
html_count=$(ls -1 ${OUTPUT_DIR}/*.html 2>/dev/null | wc -l | tr -d ' ')

echo "Output folder: ${OUTPUT_DIR}"
echo "  ${yaml_count} simulations"
echo "  ${html_count} visualizations"
echo ""
echo "=========================================="
echo "All examples completed successfully!"
echo "=========================================="
