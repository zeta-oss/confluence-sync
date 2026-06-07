#!/usr/bin/env bash
# Post-release consumer dry-run validation (L6).
# Usage: ./scripts/verify-consumers.sh  (or: make verify-consumers)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib.sh
source "${REPO_ROOT}/scripts/lib.sh"

STRATEGY_ROOT="${STRATEGY_ROOT:-${HOME}/Git/zeta-ai-product-strategy}"
WRITING_WORK_ROOT="${WRITING_WORK_ROOT:-${HOME}/Git/writing-work}"

ensure_venv "${REPO_ROOT}"
load_confluence_env

if [[ -z "${CONFLUENCE_TOKEN:-}" ]]; then
  echo "ERROR: CONFLUENCE_TOKEN not set. Add to ~/.local/confluence-sync/.env"
  exit 1
fi

CLI="$(_confluence_sync_cli)"

echo "── verify consumers ──"

echo "[1/3] doctor — ${STRATEGY_ROOT}"
"${CLI}" doctor --project-root "${STRATEGY_ROOT}"

echo "[2/3] dry-run sync foundry-cto — ${STRATEGY_ROOT}"
"${CLI}" sync -d foundry-cto --dry-run --project-root "${STRATEGY_ROOT}"

echo "[3/3] dry-run sync term-deposits-tda — ${WRITING_WORK_ROOT}"
"${CLI}" sync -d term-deposits-tda --dry-run --project-root "${WRITING_WORK_ROOT}"

echo ""
echo "✓ Consumer verification passed"
