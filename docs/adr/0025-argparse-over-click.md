# 0025. Argparse over Click for CLI

**Status:** Accepted
**Date:** 2026-06-01

## Context

The CLI needs subcommands (`sync`, `init`, `doctor`, `smoke`) with flags and help text. Options: `click`, `typer`, Python stdlib `argparse`.

## Decision

Use Python stdlib `argparse` instead of `click` or `typer`.

Reasons:
- **Zero extra dependency**: `click` would be a runtime dep for something with no user-facing interactive prompt requirements
- **Full control**: argparse is sufficient for the flag set needed
- **No magic**: argparse's explicit parser construction is easy to read and test

The CLI module (`cli.py`) builds a parser tree and routes to subcommand functions in `commands/`.

## Consequences

- `click` is not in `pyproject.toml` dependencies
- Subcommands are implemented as plain functions, not decorators
- Test subprocess output is checked against argparse's standard help format
