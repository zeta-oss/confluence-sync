# 0016. Project-local `.confluence-sync/` Directory

**Status:** Accepted
**Date:** 2026-06-01

## Context

After extracting the sync scripts into a standalone CLI (ADR 0015), we need a convention for where each consuming repo stores its configuration, sync state, and gitignored local data.

## Decision

Each Git repo that uses `confluence-sync` stores its config in a `.confluence-sync/` directory at the project root (next to `.git/`):

```
.confluence-sync/
├── confluence-sync.yml    # committed config
├── .gitignore             # ignores destinations/
└── destinations/          # local state, gitignored
    └── {dest-id}/
        └── sync-state.jsonl
```

The CLI always resolves `project_root` by walking up from `cwd` to find `.git/`.

## Consequences

- Config travels with the code, not with the scripts
- State is local-only and never committed (gitignored)
- Multiple repos can each have independent `.confluence-sync/` with no coordination
- Replaces `_confluence_sync/data/confluence-destinations.yaml`
