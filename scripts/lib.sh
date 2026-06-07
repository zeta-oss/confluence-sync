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
  local stamp
  stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mkdir -p "${HOME}/.local/confluence-sync"
  echo "${stamp}" > "${HOME}/.local/confluence-sync/smoke-last-pass"
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
