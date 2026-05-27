#!/bin/bash
set -euo pipefail

# Install each pinned dependency from its git-fetched source folder.
# --no-deps because all transitive deps are declared in meta.yaml run requirements.
# Install order matters: mom6_forge before regional_mom6 (rm6 depends on it).
$PYTHON -m pip install _deps/mom6_forge --no-deps --ignore-installed -vv
$PYTHON -m pip install _deps/regional_mom6 --no-deps --ignore-installed -vv
$PYTHON -m pip install _deps/ipyfilechooser --no-deps --ignore-installed -vv
$PYTHON -m pip install _deps/visualCaseGen --no-deps --ignore-installed -vv
$PYTHON -m pip install . --no-deps --ignore-installed -vv
