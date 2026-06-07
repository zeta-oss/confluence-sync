# 0024. Test Cleanup Policy

**Status:** Accepted
**Date:** 2026-06-01

## Context

Tests that create Git repos, state directories, or Confluence pages must clean up after themselves. Without explicit policy, tests can leave stale data in:
- The user's home directory (`~/.local/confluence-sync/`)
- The filesystem (temp Git repos)
- Confluence (live smoke pages)

## Decision

### Filesystem cleanup

All test-created Git repos and state directories are created inside `pytest tmp_path` / `tmp_path_factory`. Pytest auto-deletes these after each test.

An `autouse` fixture in `conftest.py` monkeypatches `HOME` and `Path.home()` to point to `tmp_path` so no test ever touches `~/.local/confluence-sync/`.

### Confluence cleanup

Live smoke tests follow a strict cleanup sequence:
1. `smoke reset` — delete all pages under the smoke root page before the run
2. After `smoke verify` completes (pass or fail), `smoke_cleanup.delete_smoke_pages()` is called unconditionally

`smoke_cleanup.py` deletes Confluence pages via the API and wipes the local state directory.

### No orphaned temp files

Tests must not write outside `tmp_path`. Fixture `fake_home` ensures this for `~/.local/`. Tests that create projects must use `fake_project_root` (which uses `tmp_path`).

## Consequences

- Tests are safe to run on any machine
- CI does not accumulate stale Confluence pages
- `conftest.py` `autouse` fixtures enforce isolation without per-test boilerplate
