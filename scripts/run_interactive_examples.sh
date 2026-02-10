#!/bin/bash
# Run interactive examples that ask the user to resolve uncertainty
# Usage: ./scripts/run_interactive_examples.sh
#
# These examples use --ask-threshold with a low value so that the
# simulation pauses and asks you to specify unknown attribute values.
# After answering, pruned branches appear grayed out in the visualization.

set -e

echo "=========================================="
echo "World Simulator - Interactive Examples"
echo "=========================================="
echo ""
echo "These examples will pause and ask you questions"
echo "about uncertain attribute values during simulation."
echo ""

# Create output directory
OUTPUT_DIR="outputs/interactive"
mkdir -p "$OUTPUT_DIR"
mkdir -p outputs/histories

# Helper: run interactive simulation and generate visualization
run_interactive() {
    local name=$1
    shift

    echo "-------------------------------------------"
    echo "  Running: $name"
    echo "-------------------------------------------"
    uv run sim simulate "$@" --name "$name"

    # Move history and generate visualization
    if [ -f "outputs/histories/${name}.yaml" ]; then
        mv "outputs/histories/${name}.yaml" "${OUTPUT_DIR}/${name}.yaml"
        echo "  Generating visualization..."
        uv run sim visualize "${OUTPUT_DIR}/${name}.yaml" -o "${OUTPUT_DIR}/${name}.html" --no-open
        echo "  -> ${OUTPUT_DIR}/${name}.html"
    fi
    echo ""
}

echo ""
echo "1. FLASHLIGHT - Unknown Battery (turn_on + shake)"
echo "   The battery level is unknown. After branching, you'll be asked"
echo "   what the actual battery level is."
echo ""

run_interactive interactive_flashlight_shake \
    --obj flashlight \
    --set battery.level=unknown \
    --actions turn_on shake \
    --ask-threshold 3

echo ""
echo "2. FLASHLIGHT - Unknown Battery (turn_on + turn_off + turn_on)"
echo "   Three-action cycle with unknown battery. The question reduces"
echo "   the exponential branching before it gets out of hand."
echo ""

run_interactive interactive_flashlight_cycle \
    --obj flashlight \
    --set battery.level=unknown \
    --actions turn_on turn_off turn_on \
    --ask-threshold 4

echo ""
echo "3. COFFEE MACHINE - Multiple Unknowns"
echo "   Water level, bean amount, and heater temperature are all unknown."
echo "   You'll be asked about the most uncertain attribute."
echo ""

run_interactive interactive_coffee \
    --obj coffee_machine \
    --set water_tank.level=unknown bean_hopper.amount=unknown heater.temperature=unknown \
    --actions brew_espresso \
    --ask-threshold 5

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
echo "Open any HTML file in your browser to see the result."
echo "Pruned branches appear grayed out in the visualization."
echo ""
echo "=========================================="
echo "Interactive examples completed!"
echo "=========================================="
