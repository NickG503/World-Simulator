#!/bin/bash
#
# Run all examples from EXAMPLES.md and generate visualizations
# Usage: ./scripts/run_examples.sh
#
# Outputs:
#   - YAML histories: outputs/histories/
#   - HTML visualizations: outputs/visualizations/
#

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          World Simulator - Running All Examples                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Create output directories
mkdir -p outputs/histories
mkdir -p outputs/visualizations

# Clean up old files
echo -e "${YELLOW}🧹 Cleaning up old files...${NC}"
rm -f outputs/histories/*.yaml 2>/dev/null || true
rm -f outputs/visualizations/*.html 2>/dev/null || true
echo ""

# ============================================================================
# VALIDATION & INSPECTION
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 VALIDATION & INSPECTION${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ Validating knowledge base...${NC}"
uv run sim validate
echo ""

echo -e "${YELLOW}▶ Showing flashlight object...${NC}"
uv run sim show object flashlight
echo ""

echo -e "${YELLOW}▶ Showing flashlight behaviors...${NC}"
uv run sim show behaviors flashlight
echo ""

echo -e "${YELLOW}▶ Showing TV behaviors...${NC}"
uv run sim show behaviors tv
echo ""

# ============================================================================
# BASIC SIMULATIONS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎮 BASIC SIMULATIONS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ Flashlight on/off cycle...${NC}"
uv run sim simulate --obj flashlight turn_on turn_off --name basic_flashlight
echo ""

echo -e "${YELLOW}▶ TV simple session...${NC}"
uv run sim simulate --obj tv turn_on adjust_volume=medium turn_off --name tv_simple
echo ""

echo -e "${YELLOW}▶ Kettle simple workflow...${NC}"
uv run sim simulate --obj kettle pour_water=full heat turn_off --name kettle_simple
echo ""

# ============================================================================
# USING PARAMETERS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}⚙️ USING PARAMETERS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ Kettle pour different amounts...${NC}"
uv run sim simulate --obj kettle pour_water=full --name kettle_full
uv run sim simulate --obj kettle pour_water=medium --name kettle_medium
echo ""

echo -e "${YELLOW}▶ TV volume adjustment...${NC}"
uv run sim simulate --obj tv turn_on adjust_volume=high turn_off --name tv_volume_high
echo ""

echo -e "${YELLOW}▶ Flashlight with new battery...${NC}"
uv run sim simulate --obj flashlight replace_battery=high turn_on --name flashlight_new_battery
echo ""

echo -e "${YELLOW}▶ TV multiple adjustments...${NC}"
uv run sim simulate --obj tv turn_on adjust_volume=low adjust_volume=high change_channel=medium turn_off --name tv_adjustments
echo ""

# ============================================================================
# MULTI-ACTION SEQUENCES
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🔄 MULTI-ACTION SEQUENCES${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ Flashlight battery cycle...${NC}"
uv run sim simulate --obj flashlight turn_on turn_off turn_on turn_off --name flashlight_cycle
echo ""

echo -e "${YELLOW}▶ TV evening session...${NC}"
uv run sim simulate --obj tv turn_on open_streaming adjust_volume=high change_channel=medium smart_adjust turn_off --name tv_evening
echo ""

echo -e "${YELLOW}▶ Kettle morning routine...${NC}"
uv run sim simulate --obj kettle pour_water=full heat turn_off --name kettle_morning
echo ""

# ============================================================================
# FAILURE HANDLING
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}⚠️ FAILURE HANDLING${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ TV change channel while off (will fail)...${NC}"
uv run sim simulate --obj tv change_channel=medium --name tv_fail_demo
echo ""

echo -e "${YELLOW}▶ Flashlight drain then turn on (will fail)...${NC}"
uv run sim simulate --obj flashlight drain_battery turn_on --name flashlight_empty_fail
echo ""

echo -e "${YELLOW}▶ TV with factory reset...${NC}"
uv run sim simulate --obj tv turn_on turn_off factory_reset turn_on --name tv_with_reset
echo ""

# ============================================================================
# VIEWING RESULTS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📊 VIEWING RESULTS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ View flashlight cycle history...${NC}"
uv run sim history flashlight_cycle
echo ""

echo -e "${YELLOW}▶ View TV evening history...${NC}"
uv run sim history tv_evening
echo ""

echo -e "${YELLOW}▶ View failure demo history...${NC}"
uv run sim history tv_fail_demo
echo ""

# ============================================================================
# GENERATE VISUALIZATIONS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🌐 GENERATING VISUALIZATIONS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}▶ Generating visualizations for all histories...${NC}"
for yaml_file in outputs/histories/*.yaml; do
    if [ -f "$yaml_file" ]; then
        name=$(basename "$yaml_file" .yaml)
        output_html="outputs/visualizations/${name}.html"
        echo "  → Generating $name.html..."
        uv run sim visualize "$name" --no-open -o "$output_html"
    fi
done
echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}Generated files:${NC}"
echo ""
echo "History YAML files (outputs/histories/):"
ls outputs/histories/*.yaml 2>/dev/null | while read f; do echo "  $(basename $f)"; done
echo ""
echo "Visualization HTML files (outputs/visualizations/):"
ls outputs/visualizations/*.html 2>/dev/null | while read f; do echo "  $(basename $f)"; done
echo ""

# Count files
yaml_count=$(ls outputs/histories/*.yaml 2>/dev/null | wc -l | tr -d ' ')
html_count=$(ls outputs/visualizations/*.html 2>/dev/null | wc -l | tr -d ' ')

echo -e "${GREEN}Total: $yaml_count history files, $html_count visualizations${NC}"
echo ""
echo -e "${YELLOW}To view a history:${NC} uv run sim history <name>"
echo -e "${YELLOW}To open a visualization:${NC} open outputs/visualizations/<name>.html"
echo ""
echo -e "${GREEN}✨ All examples complete!${NC}"
echo ""
