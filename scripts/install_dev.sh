#!/bin/bash
# Full development setup: pip install -e . + ArduPilot SITL
# Run from project root: ./scripts/install_dev.sh

set -e
cd "$(dirname "$0")/.."

echo "Installing aerpawlib with all dependencies..."
pip install -e .

echo ""
echo "Setting up ArduPilot SITL..."
aerpawlib-setup-sitl

echo ""
echo "Done. ARDUPILOT_HOME is set to ./ardupilot (or set it explicitly)."
