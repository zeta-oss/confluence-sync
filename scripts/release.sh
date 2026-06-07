#!/usr/bin/env bash
# Full release workflow for confluence-sync.
# Usage: ./scripts/release.sh 0.2.0  (or: make release VERSION=0.2.0)
#
# Steps (abort on first failure):
# 1. Verify clean git status on main
# 2. release-preflight (token, mmdc, brew, recent make smoke)
# 3. Bump version in pyproject.toml + __init__.py; update CHANGELOG.md
# 4. make test (coverage gate)
# 5. Require mmdc on PATH (doctor check)
# 6. Trap EXIT → smoke reset
# 7. confluence-sync smoke run (live)
# 8. hatch build (sdist tarball)
# 9. ./scripts/publish-brew.sh
# 10. brew test --formula
# 11. Commit + tag + push
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib.sh
source "${REPO_ROOT}/scripts/lib.sh"
VERSION="${1:-}"

if [[ -z "${VERSION}" ]]; then
  echo "Usage: $0 <version>"
  exit 1
fi

TAG="v${VERSION}"
cd "${REPO_ROOT}"

# --- Step 1: clean status on main ---
BRANCH=$(git branch --show-current)
if [[ "${BRANCH}" != "main" ]]; then
  echo "ERROR: Must be on main branch (current: ${BRANCH})"
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree is not clean. Commit or stash changes first."
  exit 1
fi

# --- Step 2: preflight ---
echo "[2/11] Running release preflight..."
run_release_preflight

# --- Step 3: bump version ---
echo "[3/11] Bumping version to ${VERSION}..."
python3 - <<EOF
import re, pathlib

# pyproject.toml
p = pathlib.Path("pyproject.toml")
p.write_text(re.sub(r'^version = ".*"', f'version = "${VERSION}"', p.read_text(), flags=re.MULTILINE))

# __init__.py
i = pathlib.Path("src/confluence_sync/__init__.py")
i.write_text(re.sub(r'__version__ = ".*"', f'__version__ = "${VERSION}"', i.read_text()))

print(f"  Bumped to ${VERSION}")
EOF

# Update CHANGELOG placeholder
if grep -q "\[Unreleased\]" CHANGELOG.md 2>/dev/null; then
  today=$(date +%Y-%m-%d)
  sed -i.bak "s/\[Unreleased\]/[${VERSION}] - ${today}/" CHANGELOG.md
  rm -f CHANGELOG.md.bak
fi

# --- Step 4: tests ---
echo "[4/11] Running tests..."
ensure_venv "${REPO_ROOT}"
run_tests

# --- Step 5: mermaid check ---
echo "[5/11] Checking mermaid-cli..."
if ! command -v mmdc &>/dev/null; then
  if ! npx --yes @mermaid-js/mermaid-cli --version &>/dev/null 2>&1; then
    echo "ERROR: mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli"
    exit 1
  fi
fi

# --- Step 6: trap for smoke reset ---
echo "[6/11] Registering smoke reset trap..."
trap 'run_smoke_reset' EXIT

# --- Step 7: live smoke ---
echo "[7/11] Running live smoke..."
run_live_smoke

# --- Step 8: build ---
echo "[8/11] Building dist..."
run_build

# --- Step 9: update formula ---
echo "[9/11] Updating Homebrew formula..."
./scripts/publish-brew.sh "${VERSION}"

# --- Step 10: brew test ---
echo "[10/11] Testing formula..."
FORMULA_BACKUP="$(mktemp)"
FORMULA_PATH="${REPO_ROOT}/Formula/confluence-sync.rb"
cp "${FORMULA_PATH}" "${FORMULA_BACKUP}"

TARBALL_PATH="${REPO_ROOT}/dist/confluence_sync-${VERSION}.tar.gz"
if [[ ! -f "${TARBALL_PATH}" ]]; then
  TARBALL_PATH="${REPO_ROOT}/dist/confluence-sync-${VERSION}.tar.gz"
fi
ABS_TARBALL="$(cd "$(dirname "${TARBALL_PATH}")" && pwd)/$(basename "${TARBALL_PATH}")"

python3 -c "
import re
from pathlib import Path
path = Path('${FORMULA_PATH}')
content = path.read_text(encoding='utf-8')
new_content = re.sub(r'^\s*url\s+\".*?\"', '  url \"file://${ABS_TARBALL}\"', content, count=1, flags=re.MULTILINE)
path.write_text(new_content, encoding='utf-8')
"

if run_brew_test; then
  cp "${FORMULA_BACKUP}" "${FORMULA_PATH}"
  rm -f "${FORMULA_BACKUP}"
else
  cp "${FORMULA_BACKUP}" "${FORMULA_PATH}"
  rm -f "${FORMULA_BACKUP}"
  echo "ERROR: brew test failed"
  exit 1
fi

# --- Step 11: commit + tag + push ---
echo "[11/11] Committing and tagging..."
git add pyproject.toml src/confluence_sync/__init__.py Formula/confluence-sync.rb CHANGELOG.md
git commit -m "chore(release): v${VERSION}"
git tag "${TAG}"
echo ""
echo "✓ Release v${VERSION} ready."
echo "  Push with: git push && git push --tags"
echo "  Then: gh release create ${TAG} dist/*"
