#!/usr/bin/env bash
# publish-brew.sh — Update Formula/confluence-sync.rb url + sha256
# Usage: ./scripts/publish-brew.sh 0.2.0
#
# Computes SHA256 from local dist/*.tar.gz or GitHub archive URL.
# Rewrites Formula url and sha256 fields in-place.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Usage: ./scripts/publish-brew.sh VERSION"
  exit 1
fi

FORMULA="Formula/confluence-sync.rb"
TARBALL_URL="https://github.com/zeta-oss/confluence-sync/archive/refs/tags/v${VERSION}.tar.gz"

echo "Updating formula for v${VERSION}..."

# Try local dist tarball first
LOCAL_TARBALL=$(ls dist/confluence_sync-${VERSION}.tar.gz 2>/dev/null || ls dist/confluence-sync-${VERSION}.tar.gz 2>/dev/null || true)

if [ -n "$LOCAL_TARBALL" ] && [ -f "$LOCAL_TARBALL" ]; then
  echo "  Using local tarball: $LOCAL_TARBALL"
  SHA256=$(shasum -a 256 "$LOCAL_TARBALL" | awk '{print $1}')
else
  echo "  Downloading from GitHub to compute SHA256..."
  TMPFILE=$(mktemp)
  curl -sSL "$TARBALL_URL" -o "$TMPFILE"
  SHA256=$(shasum -a 256 "$TMPFILE" | awk '{print $1}')
  rm -f "$TMPFILE"
fi

echo "  URL:    $TARBALL_URL"
echo "  SHA256: $SHA256"

# Rewrite url and sha256 in formula
sed -i '' "s|url \".*\"|url \"${TARBALL_URL}\"|" "$FORMULA"
sed -i '' "s|sha256 \".*\"|sha256 \"${SHA256}\"|" "$FORMULA"

echo "✓ Formula updated: $FORMULA"
