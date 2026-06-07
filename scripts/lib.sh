#!/usr/bin/env bash
# Shared helpers for confluence-sync shell scripts.
# Source from repo scripts: source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

_confluence_sync_repo_root() {
  local lib_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  echo "$(cd "${lib_dir}/.." && pwd)"
}

ensure_venv() {
  local repo_root="${1:-$(_confluence_sync_repo_root)}"
  if [[ ! -x "${repo_root}/.venv/bin/python" ]]; then
    echo "Dev venv missing. Running bootstrap..."
    "${repo_root}/scripts/bootstrap-dev.sh"
  fi
}

run_nox() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  if [[ -x "${repo_root}/.venv/bin/nox" ]]; then
    "${repo_root}/.venv/bin/nox" "$@"
  elif command -v nox &>/dev/null; then
    nox "$@"
  else
    echo "ERROR: nox not found. Run: make install"
    return 127
  fi
}

run_tests() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  make -C "${repo_root}" test
}

run_build() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  "${repo_root}/.venv/bin/pip" install -q hatch 2>/dev/null || true
  "${repo_root}/.venv/bin/hatch" build
}

load_confluence_env() {
  local env_file="${HOME}/.local/confluence-sync/.env"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

_confluence_sync_smoke_config() {
  local repo_root="${1:-$(_confluence_sync_repo_root)}"
  echo "${repo_root}/tests/live_smoke/confluence-sync.yml"
}

_confluence_sync_cli() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  echo "${repo_root}/.venv/bin/confluence-sync"
}

run_smoke_reset() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  load_confluence_env
  "$(_confluence_sync_cli)" smoke reset -d smoke-live \
    --config "$(_confluence_sync_smoke_config "${repo_root}")" || true
}

_mark_smoke_pass() {
  local repo_root stamp sha
  repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sha="$(git -C "${repo_root}" rev-parse HEAD)"
  mkdir -p "${HOME}/.local/confluence-sync"
  python3 - <<PY
import json
from pathlib import Path

payload = {"timestamp": "${stamp}", "sha": "${sha}"}
Path("${HOME}/.local/confluence-sync/smoke-last-pass").write_text(
    json.dumps(payload) + "\n", encoding="utf-8"
)
PY
}

assert_clean_main() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  local branch
  branch="$(git -C "${repo_root}" branch --show-current)"
  if [[ "${branch}" != "main" ]]; then
    echo "ERROR: Must be on main branch (current: ${branch})"
    return 1
  fi
  if ! git -C "${repo_root}" diff --quiet || ! git -C "${repo_root}" diff --cached --quiet; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first."
    return 1
  fi
}

check_mmdc() {
  if command -v mmdc &>/dev/null; then
    return 0
  fi
  if npx --yes @mermaid-js/mermaid-cli --version &>/dev/null 2>&1; then
    return 0
  fi
  echo "ERROR: mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli"
  return 1
}

run_release_preflight() {
  "${REPO_ROOT:-$(_confluence_sync_repo_root)}/scripts/release-preflight.sh"
}

run_live_smoke() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  load_confluence_env
  if [[ -z "${CONFLUENCE_TOKEN:-}" ]]; then
    echo "ERROR: CONFLUENCE_TOKEN not set. Add to ~/.local/confluence-sync/.env"
    return 1
  fi
  if "$(_confluence_sync_cli)" smoke run -d smoke-live \
      --config "$(_confluence_sync_smoke_config "${repo_root}")"; then
    _mark_smoke_pass
    return 0
  fi
  return 1
}

run_brew_test() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  brew test --formula "${repo_root}/Formula/confluence-sync.rb"
}
