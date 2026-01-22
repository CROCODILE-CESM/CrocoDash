#!/bin/bash
set -e

REPO_URL="${1:-https://github.com/CROCODILE-CESM/CESM.git}"
CHECKOUT_DIR="${2:-cesm}"
FLEXIMOD="$CHECKOUT_DIR/bin/git-fleximod"

if [ ! -d "$CHECKOUT_DIR" ]; then
    git clone "$REPO_URL" "$CHECKOUT_DIR"
    (cd "$CHECKOUT_DIR" && ./bin/git-fleximod update)
else
    echo "Directory '$CHECKOUT_DIR' already exists. Skipping clone."
fi




