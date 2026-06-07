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

run_live_smoke() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  ensure_venv "${repo_root}"
  load_confluence_env
  if [[ -z "${CONFLUENCE_TOKEN:-}" ]]; then
    echo "ERROR: CONFLUENCE_TOKEN not set. Add to ~/.local/confluence-sync/.env"
    return 1
  fi
  "${repo_root}/.venv/bin/confluence-sync" smoke run -d smoke-live
}

run_brew_test() {
  local repo_root="${REPO_ROOT:-$(_confluence_sync_repo_root)}"
  brew test --formula "${repo_root}/Formula/confluence-sync.rb"
}
