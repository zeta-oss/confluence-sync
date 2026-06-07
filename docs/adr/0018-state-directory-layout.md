# 0018. State Directory Layout — `destinations/{id}/`

**Status:** Accepted (supersedes ADR 0003)
**Date:** 2026-06-01

## Context

ADR 0003 established a `_confluence_sync/data/{id}/` layout inside the strategy repo. With the move to a project-local `.confluence-sync/` directory (ADR 0016), the state layout needs updating.

## Decision

State for each destination is stored at:

```
{project_root}/.confluence-sync/destinations/{dest_id}/
```

Files in each destination dir:
- `sync-state.jsonl` — append-only JSONL of page state entries
- `sync-metadata.json` — last run metadata (optional)
- `sync-report-*.md` — sync reports (optional)

The `.confluence-sync/.gitignore` file always contains `destinations/`.

An explicit `--state-dir` CLI flag overrides the default.

## Consequences

- State is co-located with config but gitignored
- Destination ID is the directory name — changing a destination ID moves the state
- Compatible format with the old `_confluence_sync/data/{id}/` — files can be copied as-is
