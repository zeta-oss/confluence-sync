# 0024. Test Cleanup Policy

**Status:** Accepted
**Date:** 2026-06-01 (updated 2026-06-07)

## Context

Tests that create Git repos, state directories, or Confluence pages must clean up after themselves. Without explicit policy, tests can leave stale data in:

- The user's home directory (`~/.local/confluence-sync/`)
- The filesystem (temp Git repos)
- Confluence (live smoke spaces)

## Decision

### Filesystem cleanup

All test-created Git repos and state directories are created inside `pytest tmp_path` / `tmp_path_factory`. Pytest auto-deletes these after each test.

An `autouse` fixture in `conftest.py` monkeypatches `HOME` and `Path.home()` to point to `tmp_path` so no test ever touches `~/.local/confluence-sync/`.

Shell script tests (`tests/scripts/`) set `HOME` explicitly in subprocess environments for the same isolation.

### Confluence cleanup (live smoke)

Live smoke uses ephemeral workspace lifecycle via `SmokeProvisioner`:

1. **provision** — create private space `CS{run_id}` (or ephemeral root page in fallback mode); write `~/.local/confluence-sync/smoke-session.json`
2. **teardown** — `destroy_workspace()` deletes the space (or root subtree) and removes `smoke-session.json`
3. **reset / EXIT trap** — `destroy_session_workspace()` reads the session file and destroys any workspace left from an interrupted run

`SmokeCleanup.wipe_local_state()` clears project-local sync state during smoke runs. Confluence teardown runs in a `finally` block in `commands/smoke.py` (always).

### No orphaned temp files

Tests must not write outside `tmp_path`. Fixture `fake_home` ensures this for `~/.local/`. Tests that create projects must use `fake_project_root` or `git_project_root` (which use `tmp_path`).

## Consequences

- Tests are safe to run on any machine
- Interrupted smoke runs can be recovered via `make smoke` trap or `confluence-sync smoke reset`
- `conftest.py` `autouse` fixtures enforce isolation without per-test boilerplate
- Preflight detects stale `smoke-session.json` and invokes reset before release
