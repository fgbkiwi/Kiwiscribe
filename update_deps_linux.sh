#!/usr/bin/env bash
set -euo pipefail

echo "Running Kiwiscribe Safe Dependency Update (Linux)..."
echo

VENV_DIR=".venv_linux"
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"

if [[ ! -f "$ACTIVATE_SCRIPT" ]]; then
  echo "[ERROR] Virtual environment not found at $ACTIVATE_SCRIPT"
  echo "Create it first, for example: python3.13 -m venv .venv_linux"
  exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE_SCRIPT"

if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] Python is not available after activating $VENV_DIR"
  exit 1
fi

python dependency_manager.py update

echo
echo "Update process finished."
