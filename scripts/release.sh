#!/usr/bin/env bash
# Full release workflow for confluence-sync.
# Usage: ./scripts/release.sh 0.2.0  (or: make release VERSION=0.2.0)
#
# Steps (abort on first failure):
# 1. Verify clean git status on main
# 2. Bump version in pyproject.toml + __init__.py; update CHANGELOG.md
# 3. make test (coverage gate)
# 4. Require mmdc on PATH (doctor check)
# 5. Trap EXIT → smoke reset
# 6. confluence-sync smoke run (live)
# 7. hatch build (sdist tarball)
# 8. ./scripts/publish-brew.sh
# 9. brew test --formula
# 10. Commit + tag + push
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

# --- Step 2: bump version ---
echo "[1/10] Bumping version to ${VERSION}..."
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

# --- Step 3: tests ---
echo "[3/10] Running tests..."
ensure_venv "${REPO_ROOT}"
run_tests

# --- Step 4: mermaid check ---
echo "[4/10] Checking mermaid-cli..."
if ! command -v mmdc &>/dev/null; then
  if ! npx --yes @mermaid-js/mermaid-cli --version &>/dev/null 2>&1; then
    echo "ERROR: mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli"
    exit 1
  fi
fi

# --- Step 5: trap for smoke reset ---
echo "[5/10] Registering smoke reset trap..."
trap 'confluence-sync smoke reset -d smoke-live || true' EXIT

# --- Step 6: live smoke ---
echo "[6/10] Running live smoke..."
run_live_smoke

# --- Step 7: build ---
echo "[7/10] Building dist..."
run_build

# --- Step 8: update formula ---
echo "[8/10] Updating Homebrew formula..."
./scripts/publish-brew.sh "${VERSION}"

# --- Step 9: brew test ---
echo "[9/10] Testing formula..."
run_brew_test

# --- Step 10: commit + tag + push ---
echo "[10/10] Committing and tagging..."
git add pyproject.toml src/confluence_sync/__init__.py Formula/confluence-sync.rb CHANGELOG.md
git commit -m "chore(release): v${VERSION}"
git tag "${TAG}"
echo ""
echo "✓ Release v${VERSION} ready."
echo "  Push with: git push && git push --tags"
echo "  Then: gh release create ${TAG} dist/*"
