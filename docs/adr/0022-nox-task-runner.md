# 0022. Nox as Task Runner

**Status:** Accepted
**Date:** 2026-06-01

## Context

The project needs a task runner for: unit tests, lint, live smoke tests, build, and Homebrew formula test. Options: `tox`, `nox`, `Makefile`.

## Decision

Use `nox` for all task automation, with a thin `Makefile` wrapper for convenience.

Nox sessions defined in `noxfile.py`:
- `test` — unit, integration, CLI tests in an isolated venv
- `lint` — ruff check + ruff format
- `live_smoke` — live smoke test (requires `CONFLUENCE_TOKEN`)
- `build` — sdist + wheel
- `brew_test` — Homebrew formula test

The `Makefile` simply delegates: `make test` → `nox -s test`.

Reasons:
- Nox uses Python functions (no INI-file magic)
- Each session creates an isolated venv — no cross-contamination
- `nox -l` lists all available sessions
- Works well with CI (GitHub Actions)

## Consequences

- `pip install nox` required globally (or via `scripts/bootstrap-dev.sh`)
- `nox` replaces `tox` — no `tox.ini` needed
