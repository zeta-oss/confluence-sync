#!/usr/bin/env bash
# Verify release prerequisites before version bump.
# Usage: ./scripts/release-preflight.sh  (or: make release-preflight)
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=lib.sh
source "${REPO_ROOT}/scripts/lib.sh"

SMOKE_GATE_MAX_AGE_HOURS="${SMOKE_GATE_MAX_AGE_HOURS:-168}"  # 7 days

_fail() {
  echo "ERROR: $*" >&2
  exit 1
}

echo "── release preflight ──"

# Dev environment
ensure_venv "${REPO_ROOT}"
if [[ ! -x "${REPO_ROOT}/.venv/bin/confluence-sync" ]]; then
  _fail "confluence-sync CLI not installed. Run: make install"
fi
echo "  ✓ Dev venv ready"

# Credentials
load_confluence_env
if [[ -z "${CONFLUENCE_TOKEN:-}" ]]; then
  _fail "CONFLUENCE_TOKEN not set. Add to ~/.local/confluence-sync/.env"
fi
echo "  ✓ CONFLUENCE_TOKEN set"

# Smoke config + fixture
smoke_config="$(_confluence_sync_smoke_config "${REPO_ROOT}")"
if [[ ! -f "${smoke_config}" ]]; then
  _fail "Smoke config missing: ${smoke_config}"
fi
if [[ ! -d "${REPO_ROOT}/tests/live_smoke/fixture" ]]; then
  _fail "Smoke fixture missing: tests/live_smoke/fixture"
fi
echo "  ✓ Smoke config and fixture present"

# Recent successful smoke (make smoke gate) — JSON {timestamp, sha} required
smoke_pass_file="${HOME}/.local/confluence-sync/smoke-last-pass"
if [[ ! -f "${smoke_pass_file}" ]]; then
  _fail "No recorded smoke pass. Run: make smoke"
fi
if ! smoke_gate_output="$(python3 - <<PY
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

path = Path("""${smoke_pass_file}""")
raw = path.read_text(encoding="utf-8").strip()
allow_stale_sha = """${SMOKE_GATE_ALLOW_STALE_SHA:-}""" == "1"
head_sha = subprocess.check_output(
    ["git", "-C", """${REPO_ROOT}""", "rev-parse", "HEAD"], text=True
).strip()
max_age = timedelta(hours=${SMOKE_GATE_MAX_AGE_HOURS})

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    # Legacy plain timestamp (pre SHA gate)
    if raw and "T" in raw and raw[0].isdigit():
        print("legacy", file=sys.stderr)
        sys.exit(3)
    print("invalid", file=sys.stderr)
    sys.exit(1)

if not isinstance(data, dict):
    sys.exit(1)
ts_raw = data.get("timestamp")
recorded_sha = data.get("sha")
if not ts_raw or not recorded_sha:
    sys.exit(1)
try:
    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
except ValueError:
    sys.exit(1)
if ts.tzinfo is None:
    ts = ts.replace(tzinfo=timezone.utc)
age = datetime.now(timezone.utc) - ts
if age > max_age:
    print(f"stale_ts:{ts_raw}", file=sys.stderr)
    sys.exit(2)
if recorded_sha != head_sha:
    if allow_stale_sha:
        print(f"stale_sha_allowed:{recorded_sha}!={head_sha}", file=sys.stderr)
    else:
        print(f"stale_sha:{recorded_sha}!={head_sha}", file=sys.stderr)
        sys.exit(4)
print(f"{ts_raw}|{recorded_sha}")
PY
)"; then
  rc=$?
  if [[ "${rc}" -eq 2 ]]; then
    _fail "Smoke pass is older than ${SMOKE_GATE_MAX_AGE_HOURS}h. Re-run: make smoke"
  fi
  if [[ "${rc}" -eq 3 ]]; then
    _fail "Legacy smoke-last-pass format (timestamp only). Re-run: make smoke"
  fi
  if [[ "${rc}" -eq 4 ]]; then
    _fail "Smoke pass SHA does not match current commit. Re-run: make smoke (or set SMOKE_GATE_ALLOW_STALE_SHA=1 for doc-only changes)"
  fi
  _fail "Invalid smoke-last-pass in ${smoke_pass_file}. Re-run: make smoke"
fi
smoke_ts="${smoke_gate_output%%|*}"
smoke_sha="${smoke_gate_output#*|}"
if [[ "${SMOKE_GATE_ALLOW_STALE_SHA:-}" == "1" && "${smoke_sha}" != "$(git -C "${REPO_ROOT}" rev-parse HEAD)" ]]; then
  echo "  ⚠ Smoke SHA mismatch allowed (SMOKE_GATE_ALLOW_STALE_SHA=1)"
fi
echo "  ✓ Recent smoke pass recorded (${smoke_ts}, sha ${smoke_sha:0:8})"

# Stale ephemeral workspace from interrupted run
if [[ -f "${HOME}/.local/confluence-sync/smoke-session.json" ]]; then
  echo "  ⚠ Stale smoke session found — running smoke reset..."
  run_smoke_reset
fi

# Mermaid CLI
if ! command -v mmdc &>/dev/null; then
  if ! npx --yes @mermaid-js/mermaid-cli --version &>/dev/null 2>&1; then
    _fail "mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli"
  fi
fi
echo "  ✓ Mermaid CLI available"

# Homebrew (formula test step)
if ! command -v brew &>/dev/null; then
  _fail "brew not found. Install Homebrew for formula test step."
fi
echo "  ✓ Homebrew available"

# Doctor check against smoke destination
if ! REPO_ROOT="${REPO_ROOT}" load_confluence_env && \
    "${REPO_ROOT}/.venv/bin/confluence-sync" doctor -d smoke-live \
      --config "${smoke_config}" >/dev/null; then
  _fail "confluence-sync doctor failed for smoke-live"
fi
echo "  ✓ doctor smoke-live passed"

echo ""
echo "✓ Release preflight passed"
echo "  Proceed with: make release VERSION=x.y.z"
