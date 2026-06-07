#!/usr/bin/env bash
# Bootstrap a local development venv for confluence-sync.
# Usage: ./scripts/bootstrap-dev.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"

echo "Creating venv at ${VENV}..."
python3 -m venv "${VENV}"

echo "Installing package in editable mode with dev extras..."
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install -e "${REPO_ROOT}[dev]"

echo ""
echo "✓ Dev environment ready."
echo "  Activate with: source ${VENV}/bin/activate"
echo "  Run tests:    make test"
