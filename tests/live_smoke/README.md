# Live Smoke Tests

Live smoke tests provision an **ephemeral Confluence workspace** automatically —
no manual CSYNC space setup required.

## How it works

Each `confluence-sync smoke run`:

1. **Creates** a private Confluence space (`CS{run_id}`) via REST API
2. Copies `fixture/` to a temp git repo and runs clean + incremental sync
3. Verifies page count, mermaid PNG, and image attachments
4. **Deletes the entire space** on teardown (even on failure)

A session file at `~/.local/confluence-sync/smoke-session.json` records the
active workspace so `smoke reset` and the release `trap EXIT` can destroy it
if the process is interrupted.

If space creation is not permitted, smoke falls back to your personal space
(`CONFLUENCE_SPACE` or `CONFLUENCE_SMOKE_FALLBACK_SPACE` in
`~/.local/confluence-sync/.env`) with a **run-unique root page and page titles**
to avoid ghost-page conflicts from Confluence's slow deletes.

## Prerequisites

```bash
# Token (required)
echo 'CONFLUENCE_TOKEN=...' >> ~/.local/confluence-sync/.env

# Fallback space if ephemeral space creation is denied (usually your personal space)
echo 'CONFLUENCE_SPACE=~5570580...' >> ~/.local/confluence-sync/.env
```

Also requires `mmdc` or `npx @mermaid-js/mermaid-cli`.

## Running

```bash
make smoke
# or:
confluence-sync smoke run -d smoke-live --config tests/live_smoke/confluence-sync.yml
```

## Fixture contents

| File | Purpose |
|------|---------|
| `docs/index.md` | Hub page with links to all other pages |
| `docs/sibling.md` | Target for relative links + incremental update |
| `docs/nested/child.md` | Deep-nested page |
| `docs/folder-link/README.md` | Directory-style link target |
| `docs/mermaid.md` | Mermaid flowchart → PNG attachment |
| `docs/images.md` | Local PNG/JPEG → Confluence attachments |
| `docs/anchors-source.md` | Cross-page anchor link source |
| `docs/anchors-target.md` | Heading anchor target |
| `.confluence-mapping.yaml` | Page titles (prefixed with run ID at runtime) |

Committed `fixture/` files are **never modified** — the smoke run copies to a
tmp dir first and patches titles there.
