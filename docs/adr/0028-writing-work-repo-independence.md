# 0028. writing-work Repo Independence

**Status:** Accepted
**Date:** 2026-06-01

## Context

The `writing-work` repository contains content (`term-deposits/`, `learnings-from-zapp-account-incident/`) that was synced to Confluence via destinations defined in the `zeta-ai-product-strategy` repo using `../writing-work/...` source paths.

This coupling meant:
- Both repos had to be checked out side-by-side
- The writing-work maintainer depended on a config they didn't own
- State for writing-work destinations was stored in the strategy repo

## Decision

`writing-work` gets its own `.confluence-sync/confluence-sync.yml` with its own destinations, using source paths local to the `writing-work` repo:

```yaml
destinations:
  - id: term-deposits-tda
    source:
      folders:
        - path: term-deposits          # relative to writing-work Git root
  - id: zapp-incident-cto
    source:
      folders:
        - path: learnings-from-zapp-account-incident
```

State moves from `zeta-ai-product-strategy/_confluence_sync/data/{id}/` to `writing-work/.confluence-sync/destinations/{id}/`.

## Consequences

- `writing-work` can be synced standalone: `cd ~/Git/writing-work && confluence-sync sync -d term-deposits-tda`
- No dependency on `zeta-ai-product-strategy` being present
- `zeta-ai-product-strategy` no longer has any `../writing-work` paths in its config
- The two repos evolve independently
