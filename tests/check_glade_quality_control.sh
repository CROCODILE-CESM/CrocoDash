#!/bin/bash
set -euo pipefail

EXEMPTIONS=(
  "CrocoDash/raw_data_access/datasets/glorys.py"
  "tests/fixtures/state.py"
  "tests/extract_obc/*"
)

echo "Checking for hardcoded '/glade' paths..."

# Build exemption pattern
exempt_pattern=$(printf "|%s" "${EXEMPTIONS[@]}")
exempt_pattern="${exempt_pattern:1}"  # remove leading '|'

# Run grep on desired directories
matches=$(grep -rnw --include="*.py" -e "/glade" CrocoDash/ tests/ demos/ || true)

# Filter out matches that are in exempted files
violations=""
while IFS= read -r line; do
  filename=$(echo "$line" | cut -d: -f1)
  if ! grep -qE "^$filename$" <(printf "%s\n" "${EXEMPTIONS[@]}"); then
    violations+="$line"$'\n'
  fi
done <<< "$matches"

if [[ -n "$violations" ]]; then
  echo "❌ Found hardcoded '/glade' paths in the following files:"
  echo "$violations"
  echo "Please remove or parameterize them. Add exemptions to tests/check_glade_quality_control.sh if necessary."
  exit 1
else
  echo "✅ No '/glade' paths found (excluding exempted files)."
fi
