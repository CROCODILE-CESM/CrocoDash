#!/usr/bin/env bash
# Install the CROCODILE packages, editable and without dependencies, into an
# environment created from stack/conda-lock.yml.
#
#   stack/install_packages.sh [CHECKOUTS_DIR]
#
# CrocoDash (with its submodules) is the repo this script lives in.
# model2obs, pyDARTdiags and dartobsgen are picked up from CHECKOUTS_DIR
# (default: the directory containing this CrocoDash checkout) if present and
# skipped otherwise, so you only need the ones you work on.
#
# --no-deps is the point: every third-party package comes from the lockfile.
# Run `pip check` afterwards to see if any package's declared range disagrees
# with the lock.
set -euo pipefail

CROCODASH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKOUTS="${1:-$(dirname "$CROCODASH")}"

install() {
    echo ">>> $1"
    python -m pip install --no-deps --no-build-isolation -e "$1"
}

# Same order as CrocoDash/environment.yml: mom6_forge before rm6.
install "$CROCODASH/CrocoDash/visualCaseGen/external/mom6_forge"
install "$CROCODASH/CrocoDash/rm6"
install "$CROCODASH/CrocoDash/visualCaseGen/external/ipyfilechooser"
install "$CROCODASH/CrocoDash/visualCaseGen"
install "$CROCODASH/gallery"
install "$CROCODASH"

for pkg in pyDARTdiags dartobsgen model2obs; do
    if [ -d "$CHECKOUTS/$pkg" ]; then
        install "$CHECKOUTS/$pkg"
    else
        echo ">>> $pkg: no checkout at $CHECKOUTS/$pkg, skipping"
    fi
done
