#!/bin/bash


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # Get this script path
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)" # Back out of tests

black \
  "$REPO_ROOT/CrocoDash/extract_forcings" \
  "$REPO_ROOT/CrocoDash/raw_data_access" \
  "$REPO_ROOT/tests" \
  "$REPO_ROOT/CrocoDash/case.py" \
  "$REPO_ROOT/CrocoDash/forcing_configurations" \
  "$REPO_ROOT/CrocoDash/logging.py"