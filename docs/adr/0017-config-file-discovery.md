# 0017. Config File Discovery — P1/P2 Fallback

**Status:** Accepted
**Date:** 2026-06-01

## Context

Some users may want a single machine-wide config (e.g. for personal use across many repos), while repos should be able to carry their own config in `.confluence-sync/`.

## Decision

Config discovery follows a two-priority search:

1. **P1 — Project-local**: `{project_root}/.confluence-sync/confluence-sync.yml`
2. **P2 — User-global**: `~/.local/confluence-sync/confluence-sync.yml`

If neither is found, `ConfigError` is raised.

An explicit `--config` CLI flag always overrides both.

## Consequences

- Project-local config (P1) takes precedence, enabling per-repo customisation
- P2 provides a fallback for personal machines with a single config
- The search is deterministic and auditable
- Mirrors the XDG base directory spirit without requiring full XDG compliance
