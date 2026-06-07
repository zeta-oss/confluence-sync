# 0027. Consumer Migration Strategy

**Status:** Accepted
**Date:** 2026-06-01

## Context

Two existing repos used the embedded `_confluence_sync/` scripts:
1. `zeta-ai-product-strategy` — 13 destinations (all sources inside the repo)
2. `writing-work` — 2 destinations (`term-deposits-tda`, `zapp-incident-cto`)

The old config (`_confluence_sync/data/confluence-destinations.yaml`) had `../writing-work/...` paths for destinations owned by `writing-work`. With the new standalone CLI, each repo must own its own config.

## Decision

### zeta-ai-product-strategy

- Create `.confluence-sync/confluence-sync.yml` with 13 destinations (all sources inside the repo — no `../writing-work` paths)
- Copy state from `_confluence_sync/data/{id}/` to `.confluence-sync/destinations/{id}/` for all 13 destinations
- Add `.confluence-sync/.gitignore` with `destinations/`
- Deprecate `_confluence_sync/README.md` with a notice pointing to the new CLI

### writing-work

- Create `.confluence-sync/confluence-sync.yml` with 2 destinations: `term-deposits-tda` and `zapp-incident-cto`
- Copy state from strategy repo's `_confluence_sync/data/{id}/` to `writing-work/.confluence-sync/destinations/{id}/`
- Source paths use local paths (`term-deposits`, `learnings-from-zapp-account-incident`) — no cross-repo paths

### Rollback

The old `_confluence_sync/` scripts remain intact and functional as a safety net during the transition period.

## Consequences

- Each repo is independently operable with `confluence-sync`
- `writing-work` can be synced without `zeta-ai-product-strategy` checked out
- State is duplicated during migration (both old and new location exist) — acceptable
