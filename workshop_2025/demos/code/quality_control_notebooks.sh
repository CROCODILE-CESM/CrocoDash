#!/bin/bash

# Exceptions for /glade paths
GLADE_EXCEPTIONS=(
  "gallery/notebooks/projects"
  "gallery/notebooks/features"   
  "gallery/notebooks/tutorials"
  "gallery/notebooks/diagnostics/cupid_output"
)

# Exceptions for s3:// paths
S3_EXCEPTIONS=(

)

## Function to filter out exceptions (files & folders)
filter_exceptions() {
  local matches="$1"
  shift
  local exceptions=("$@")
  for ex in "${exceptions[@]}"; do
    matches=$(echo "$matches" | grep -v "$ex" || true)
  done
  echo "$matches"
}

echo "Checking for hardcoded '/glade' paths..."
matches=$(grep -rnw --include="*.ipynb" -e "/glade" gallery/notebooks || true)
matches=$(filter_exceptions "$matches" "${GLADE_EXCEPTIONS[@]}")

if [[ -n "$matches" ]]; then
  echo "❌ Found hardcoded '/glade' paths in the following files:"
  echo "$matches"
  echo "Please remove or parameterize them."
  exit 1
else
  echo "✅ No '/glade' paths found."
fi

echo "Checking for hardcoded 's3://' paths..."
matches=$(grep -rnw --include="*.ipynb" -e "s3://" gallery/notebooks || true)
matches=$(filter_exceptions "$matches" "${S3_EXCEPTIONS[@]}")

if [[ -n "$matches" ]]; then
  echo "❌ Found hardcoded 's3://' paths in the following files:"
  echo "$matches"
  echo "Please remove or parameterize them."
  exit 1
else
  echo "✅ No 's3://' paths found."
fi
