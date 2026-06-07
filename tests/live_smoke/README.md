# Live Smoke Tests

This directory contains the live smoke test fixture and configuration for the
`confluence-sync smoke` subcommand.

## One-time Confluence setup

1. In `zeta-tm.atlassian.net`, create a space with key `CSYNC` (or use an existing sandbox).
2. Create a page titled `Confluence Sync Smoke` in that space.
3. Copy the page ID from the URL (`?pageId=XXXXX`) and set it in
   `tests/live_smoke/confluence-sync.yml` as `root_page_id`.
4. Ensure `CONFLUENCE_TOKEN` is set in `~/.local/confluence-sync/.env`.

## Running

```bash
make smoke    # nox -s live_smoke
# or:
confluence-sync smoke run -d smoke-live --project-root tests/live_smoke
```

## Fixture contents

The `fixture/` directory is a miniature docs repo:

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
| `assets/` | Test images committed to repo |
| `.confluence-mapping.yaml` | Unique titles to avoid space collisions |

## Cleanup

Smoke run always resets the Confluence subtree before and after the run.
Committed `fixture/` files are **never modified** — the smoke run copies to a tmp dir first.
