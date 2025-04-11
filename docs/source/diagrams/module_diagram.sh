#!/bin/bash
set -e

# Absolute path to the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pydeps "$SCRIPT_DIR/../../../CrocoDash/case.py" \
  -o "$SCRIPT_DIR/../images/module_diagram.svg" \
  --config "$SCRIPT_DIR/.pydeps"
