#!/bin/bash


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # Get this script path
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)" # Back out of tests

black "$REPO_ROOT" \
  --exclude 'CrocoDash/visualCaseGen|CrocoDash/rm6'