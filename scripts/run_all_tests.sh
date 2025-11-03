#!/bin/bash
#
# Run all unit tests for World-Simulator
#
# Usage:
#   ./scripts/run_all_tests.sh              # Run all tests
#   ./scripts/run_all_tests.sh -v           # Run with verbose output
#   ./scripts/run_all_tests.sh --coverage   # Run with coverage report
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}=== World-Simulator Test Runner ===${NC}"
echo "Project root: $PROJECT_ROOT"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Parse arguments
VERBOSE=""
COVERAGE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        --coverage)
            COVERAGE="--cov=src/simulator --cov-report=term-missing --cov-report=html"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if uv is available
if command -v uv &> /dev/null; then
    # Step 1: Check code formatting
    echo -e "${YELLOW}Step 1: Checking code formatting...${NC}"
    if ! uv run ruff format --check src/ tests/; then
        echo ""
        echo -e "${RED}✗ Code formatting check failed!${NC}"
        echo -e "${YELLOW}Run 'uv run ruff format src/ tests/' to fix formatting${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Code formatting check passed${NC}"
    echo ""

    # Step 2: Run linter
    echo -e "${YELLOW}Step 2: Running linter...${NC}"
    if ! uv run ruff check src/ tests/; then
        echo ""
        echo -e "${RED}✗ Linting failed!${NC}"
        echo -e "${YELLOW}Run 'uv run ruff check --fix src/ tests/' to fix issues${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Linting passed${NC}"
    echo ""

    # Step 3: Run tests
    echo -e "${YELLOW}Step 3: Running tests...${NC}"
    echo ""

    if uv run pytest tests/ $VERBOSE $COVERAGE; then
        echo ""
        echo -e "${GREEN}✓ All tests passed!${NC}"
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}All checks passed successfully! 🎉${NC}"
        echo -e "${GREEN}========================================${NC}"
        exit 0
    else
        echo ""
        echo -e "${RED}✗ Some tests failed${NC}"
        exit 1
    fi
else
    # Fallback to regular pytest (no formatting checks without uv)
    echo -e "${YELLOW}Running tests with pytest...${NC}"
    echo -e "${YELLOW}Note: Install 'uv' for formatting and linting checks${NC}"
    echo ""

    if pytest tests/ $VERBOSE $COVERAGE; then
        echo ""
        echo -e "${GREEN}✓ All tests passed!${NC}"
        exit 0
    else
        echo ""
        echo -e "${RED}✗ Some tests failed${NC}"
        exit 1
    fi
fi
