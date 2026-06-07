#!/usr/bin/env bash
# Full release dry-run without version bump, commit, or tag.
# Usage: ./scripts/release-rehearsal.sh  (or: make release-rehearsal)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib.sh
source "${REPO_ROOT}/scripts/lib.sh"

REHEARSAL_VERSION="${REHEARSAL_VERSION:-99.0.0-rehearsal}"
FORMULA_BACKUP=""
FORMULA_PATH="${REPO_ROOT}/Formula/confluence-sync.rb"

_restore_formula() {
  if [[ -n "${FORMULA_BACKUP}" && -f "${FORMULA_BACKUP}" ]]; then
    cp "${FORMULA_BACKUP}" "${FORMULA_PATH}"
    rm -f "${FORMULA_BACKUP}"
    FORMULA_BACKUP=""
  fi
}

cd "${REPO_ROOT}"

echo "── release rehearsal (no version bump) ──"

# --- Step 1: clean status on main ---
echo "[1/8] Verifying clean main..."
assert_clean_main

# --- Step 2: preflight ---
echo "[2/8] Running release preflight..."
run_release_preflight

# --- Step 3: tests ---
echo "[3/8] Running tests..."
run_tests

# --- Step 4: mermaid check ---
echo "[4/8] Checking mermaid-cli..."
check_mmdc

# --- Step 5: trap + live smoke ---
echo "[5/8] Registering smoke reset trap..."
trap 'run_smoke_reset' EXIT
echo "[5/8] Running live smoke..."
run_live_smoke

# --- Step 6: build ---
echo "[6/8] Building dist..."
run_build
if ! compgen -G "${REPO_ROOT}/dist/*.whl" >/dev/null; then
  echo "ERROR: No wheel found in dist/"
  exit 1
fi
if ! compgen -G "${REPO_ROOT}/dist/*.tar.gz" >/dev/null; then
  echo "ERROR: No sdist tarball found in dist/"
  exit 1
fi

# --- Step 7: publish-brew with rehearsal tarball ---
echo "[7/8] Updating Homebrew formula (rehearsal)..."
BUILT_TARBALL="$(ls "${REPO_ROOT}"/dist/confluence_sync-*.tar.gz 2>/dev/null | head -1)"
if [[ -z "${BUILT_TARBALL}" || ! -f "${BUILT_TARBALL}" ]]; then
  echo "ERROR: Could not find built sdist in dist/"
  exit 1
fi
REHEARSAL_TARBALL="${REPO_ROOT}/dist/confluence_sync-${REHEARSAL_VERSION}.tar.gz"
cp "${BUILT_TARBALL}" "${REHEARSAL_TARBALL}"

FORMULA_BACKUP="$(mktemp)"
cp "${FORMULA_PATH}" "${FORMULA_BACKUP}"
trap '_restore_formula; run_smoke_reset' EXIT

./scripts/publish-brew.sh "${REHEARSAL_VERSION}"

ABS_TARBALL="$(cd "$(dirname "${REHEARSAL_TARBALL}")" && pwd)/$(basename "${REHEARSAL_TARBALL}")"
python3 -c "
import re
from pathlib import Path
path = Path('${FORMULA_PATH}')
content = path.read_text(encoding='utf-8')
new_content = re.sub(r'^\s*url\s+\".*?\"', '  url \"file://${ABS_TARBALL}\"', content, count=1, flags=re.MULTILINE)
path.write_text(new_content, encoding='utf-8')
"

# --- Step 8: brew test ---
echo "[8/8] Testing formula..."
run_brew_test

_restore_formula
trap 'run_smoke_reset' EXIT

echo ""
echo "✓ Release rehearsal passed"
echo "  dist/ artifacts present; formula SHA matched local tarball"
echo "  No version files or git tags were modified"
