#!/bin/bash
# Checks that all notebooks under demos/gallery/notebooks/CrocoDash/ (except BGC.ipynb)
# are listed in the run_notebooks.yml matrix. Exits non-zero if any are missing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NOTEBOOK_DIR="$REPO_ROOT/demos/gallery/notebooks/CrocoDash"
WORKFLOW_FILE="$REPO_ROOT/.github/workflows/run_notebooks.yml"

# Find all notebooks, excluding .ipynb_checkpoints and BGC.ipynb
mapfile -t ALL_NOTEBOOKS < <(
  find "$NOTEBOOK_DIR" -name "*.ipynb" \
    -not -path "*/.ipynb_checkpoints/*" \
    -not -name "BGC.ipynb" \
    -not -name "add_bgc.ipynb" \
    | sort
)

# Extract matrix notebook paths (relative to demos/) from the workflow file
mapfile -t MATRIX_NOTEBOOKS < <(
  grep -oP '(?<=- )gallery/notebooks/CrocoDash/.*\.ipynb' "$WORKFLOW_FILE"
)

MISSING=()
for nb in "${ALL_NOTEBOOKS[@]}"; do
  rel_path="${nb#"$REPO_ROOT"/demos/}"
  found=false
  for matrix_nb in "${MATRIX_NOTEBOOKS[@]}"; do
    if [[ "$matrix_nb" == "$rel_path" ]]; then
      found=true
      break
    fi
  done
  if [[ "$found" == false ]]; then
    MISSING+=("$rel_path")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "ERROR: The following notebooks are not covered in run_notebooks.yml matrix:"
  for nb in "${MISSING[@]}"; do
    echo "  - $nb"
  done
  exit 1
fi

echo "All notebooks (without explicit exclusions in this script) are covered in run_notebooks.yml."
