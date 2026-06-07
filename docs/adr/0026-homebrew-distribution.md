# 0026. Homebrew Distribution Strategy

**Status:** Accepted
**Date:** 2026-06-01

## Context

macOS users expect CLI tools to be installable via Homebrew. Publishing to the official Homebrew core tap requires the tool to be widely used. We need an alternative for an org-internal tool.

## Decision

Distribute via a custom Homebrew tap hosted in the same repository:

```bash
brew tap zeta-oss/confluence-sync https://github.com/zeta-oss/confluence-sync.git
brew install confluence-sync
```

The formula is at `Formula/confluence-sync.rb` in the repo root.

`scripts/publish-brew.sh` automates updating the formula's `url` and `sha256` during a release.

A `nox -s brew_test` session runs `brew test confluence-sync` as part of the release gate.

## Consequences

- No PyPI account needed for distribution
- macOS users get a clean `confluence-sync` command without managing virtualenvs
- Formula is versioned with the code — always in sync with the release
- Linux users install via `pip install confluence-sync`
