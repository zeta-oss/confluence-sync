# 0015. Extract Sync Scripts into a Standalone Python Package

**Status:** Accepted
**Date:** 2026-06-01

## Context

The Confluence sync functionality lived as a collection of scripts inside `_confluence_sync/scripts/` within the `zeta-ai-product-strategy` repository. Multiple consumers (strategy repo, writing-work repo) referenced these scripts via relative paths or wrapper shell scripts.

Problems:
- Version skew: consumers pinned to whichever commit they last ran
- Cross-repo source paths (`../writing-work`) required both repos checked out side-by-side
- No installable entrypoint; required manual venv activation
- Tests mixed with scripts in the same directory

## Decision

Extract the sync scripts into a standalone, installable Python package: `confluence-sync`, hosted at `https://github.com/zeta-oss/confluence-sync`.

The package:
- Uses `hatchling` as the build backend
- Exposes a `confluence-sync` CLI entry point
- Is installable via `pip install confluence-sync` or Homebrew
- Has its own test suite, CI, and release process

## Consequences

- Consumers install the CLI and use `.confluence-sync/confluence-sync.yml` per repo
- No cross-repo source paths — each repo manages its own destinations
- Enables versioned releases and a Homebrew formula
- Breaking change: `_confluence_sync/` scripts are deprecated
