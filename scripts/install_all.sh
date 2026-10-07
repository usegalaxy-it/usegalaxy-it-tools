#!/bin/bash

set -u # stop if a variable is not initialized
set -e # stop in case of error
set -o pipefail # a failure of shed-tools is not hidden by the pipe to tee
shopt -s nullglob # a glob with no matches expands to nothing, not the literal pattern

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
GALAXY_SERVER="${GALAXY_SERVER:-https://vm-usegalaxy-web.elixirservices.it}"
: "${GALAXY_API_KEY:?GALAXY_API_KEY is not set}"
DRY_RUN="${DRY_RUN:-0}"
LOG="$REPO_DIR/report.log"

# Lockfiles passed as arguments, otherwise all the ones in files/
if [ $# -gt 0 ]; then
  FILES=("$@")
else
  FILES=("$REPO_DIR"/files/*.yml.lock "$REPO_DIR"/files/*.yaml.lock)
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No lockfiles found in $REPO_DIR/files"
  exit 0
fi

echo "------ Installing tools on ${GALAXY_SERVER} ------"

FAILED=()

for i in "${FILES[@]}"; do
  echo "Installing ${i}..."
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry run] shed-tools install --toolsfile $i --galaxy $GALAXY_SERVER"
    continue
  fi
  if ! shed-tools install --toolsfile "$i" --galaxy "$GALAXY_SERVER" --api_key "$GALAXY_API_KEY" 2>&1 | tee -a "$LOG"; then
    FAILED+=("$i")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "------ Failed lockfiles ------"
  printf '%s\n' "${FAILED[@]}"
  exit 1
fi
