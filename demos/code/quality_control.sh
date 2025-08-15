#!/bin/bash


## Glade Paths ##

echo "Checking for hardcoded '/glade' paths..."
# Run grep on desired directories
matches=$(grep -rnw --include="*.ipynb" -e "/glade" gallery/notebooks || true)



if [[ -n "$matches" ]]; then
  echo "❌ Found hardcoded '/glade' paths in the following files:"
  echo "$matches"
  echo "Please remove or parameterize them."
  exit 1
else
  echo "✅ No '/glade' paths found."
fi


echo "Checking for hardcoded 's3://' paths..."
# Run grep on desired directories
matches=$(grep -rnw --include="*.ipynb" -e "s3://" gallery/notebooks || true)



if [[ -n "$matches" ]]; then
  echo "❌ Found hardcoded 's3://' paths in the following files:"
  echo "$matches"
  echo "Please remove or parameterize them."
  exit 1
else
  echo "✅ No 's3://' paths found."
fi
