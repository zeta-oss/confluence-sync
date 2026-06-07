# 0021. Hatchling as Build Backend

**Status:** Accepted
**Date:** 2026-06-01

## Context

The standalone package (ADR 0015) needs a build backend to produce sdist and wheel artifacts for PyPI distribution.

Options considered: `setuptools`, `flit`, `hatchling`, `poetry`.

## Decision

Use `hatchling` as the build backend, configured in `pyproject.toml`.

Reasons:
- Modern, PEP 517/518 compliant
- Zero configuration needed for the standard `src/` layout
- No separate `setup.py` or `setup.cfg` files
- Compatible with Nox build sessions

`pyproject.toml` also centralises `pytest`, `coverage`, and `ruff` configuration (replaces `setup.cfg`, `tox.ini`, `.flake8`).

## Consequences

- `pip install -e .` works for development
- `nox -s build` produces `dist/*.whl` and `dist/*.tar.gz`
- No `requirements.txt` needed for runtime deps (declared in `pyproject.toml`)
