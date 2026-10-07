#!/bin/bash

set -u # stop if a variable is not initialized
set -e # stop in case of error
shopt -s nullglob # a glob with no matches expands to nothing, not the literal pattern

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EU_TOOLS="$REPO_DIR/usegalaxy-eu-tools"

# Initialize the submodule if it has not been checked out yet
if [ ! -f "$EU_TOOLS/scripts/fix-lockfile.py" ]; then
  git -C "$REPO_DIR" submodule update --init usegalaxy-eu-tools
fi

echo "------ Looking for updated tools ------"

cd "$REPO_DIR/files"

FILES=(*.yml *.yaml)

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No yml/yaml files found in $(pwd)"
  exit 0
fi

for i in "${FILES[@]}"; do
  echo "Fixing lockfile ${i}..."
  python3 "$EU_TOOLS/scripts/fix-lockfile.py" "$i"
done

for i in "${FILES[@]}"; do
  echo "Updating ${i}..."
  python3 "$EU_TOOLS/scripts/update-tool.py" "$i"
done
