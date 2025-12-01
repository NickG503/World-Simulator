#!/bin/bash
# Run all examples from EXAMPLES.md and generate visualizations
# Usage: ./scripts/run_examples.sh

set -e

echo "=========================================="
echo "World Simulator - Running All Examples"
echo "=========================================="

# Create output directories
mkdir -p outputs/histories
mkdir -p outputs/visualizations

# Clean previous outputs
rm -f outputs/histories/*.yaml
rm -f outputs/visualizations/*.html

echo ""
echo "1. BASIC COMMANDS"
echo "=========================================="

echo "Validating knowledge base..."
uv run sim validate

echo ""
echo "Showing flashlight object..."
uv run sim show object flashlight

echo ""
echo "Showing dice object..."
uv run sim show object dice

echo ""
echo "2. SIMPLE LINEAR SIMULATIONS"
echo "=========================================="

echo ""
echo "Flashlight basic (turn_on, turn_off)..."
uv run sim simulate --obj flashlight --actions turn_on turn_off --name flashlight_basic

echo ""
echo "Flashlight multi (turn_on, turn_off, turn_on)..."
uv run sim simulate --obj flashlight --actions turn_on turn_off turn_on --name flashlight_multi

echo ""
echo "3. SETTING INITIAL VALUES"
echo "=========================================="

echo ""
echo "Flashlight with low battery..."
uv run sim simulate --obj flashlight --set battery.level=low --actions turn_on turn_off --name flashlight_low

echo ""
echo "Flashlight with full battery..."
uv run sim simulate --obj flashlight --set battery.level=full --actions turn_on turn_off --name flashlight_full

echo ""
echo "Flashlight with empty battery (will fail turn_on)..."
uv run sim simulate --obj flashlight --set battery.level=empty --actions turn_on --name flashlight_empty

echo ""
echo "4. BRANCHING ON UNKNOWN VALUES"
echo "=========================================="

echo ""
echo "Flashlight with unknown battery (single action)..."
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on --name flashlight_unknown

echo ""
echo "Flashlight with unknown battery (full cycle)..."
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_off --name flashlight_unknown_cycle

echo ""
echo "5. ADVANCED BRANCHING WITH IN OPERATOR"
echo "=========================================="

echo ""
echo "Dice with known values (linear)..."
uv run sim simulate --obj dice --set cube.face=3 cube.color=green --actions check_win --name dice_known

echo ""
echo "Dice with unknown face and color (full branching)..."
uv run sim simulate --obj dice --set cube.face=unknown cube.color=unknown --actions check_win --name dice_branching

echo ""
echo "6. SAME ATTRIBUTE BRANCHING (INTERSECTION LOGIC)"
echo "=========================================="

echo ""
echo "Dice same attr with known value (linear)..."
uv run sim simulate --obj dice_same_attr --set cube.face=3 --actions check_win --name dice_same_known

echo ""
echo "Dice same attr with unknown face (intersection branching)..."
uv run sim simulate --obj dice_same_attr --set cube.face=unknown --actions check_win --name dice_same_branching

echo ""
echo "7. MULTI-LEVEL BRANCHING (COMPLEX)"
echo "=========================================="

echo ""
echo "Flashlight double turn_on (two levels of branching)..."
uv run sim simulate --obj flashlight --set battery.level=unknown --actions turn_on turn_on --name flashlight_double_branch

echo ""
echo "=========================================="
echo "GENERATING VISUALIZATIONS"
echo "=========================================="

# Generate visualizations for all histories
for history in outputs/histories/*.yaml; do
    name=$(basename "$history" .yaml)
    echo "Visualizing: $name"
    uv run sim visualize "$history" -o "outputs/visualizations/${name}.html" --no-open
done

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""
echo "Histories saved to: outputs/histories/"
ls -la outputs/histories/
echo ""
echo "Visualizations saved to: outputs/visualizations/"
ls -la outputs/visualizations/
echo ""
echo "=========================================="
echo "All examples completed successfully!"
echo "=========================================="
