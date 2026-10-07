#!/bin/bash

set -u # stop if a variable is not initialized
set -e # stop in case of error
shopt -s nullglob # a glob with no matches expands to nothing, not the literal pattern

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EU_TOOLS="$REPO_DIR/usegalaxy-eu-tools"
SCHEMA="$EU_TOOLS/.schema.yaml"

# Initialize the submodule if it has not been checked out yet
if [ ! -f "$SCHEMA" ]; then
  git -C "$REPO_DIR" submodule update --init usegalaxy-eu-tools
fi

FILES=("$REPO_DIR"/files/*.yml "$REPO_DIR"/files/*.yaml)

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No yml/yaml files found in $REPO_DIR/files"
  exit 0
fi

for i in "${FILES[@]}"; do
  echo "Linting ${i}..."
  pykwalify -d "$i" -s "$SCHEMA"
done
