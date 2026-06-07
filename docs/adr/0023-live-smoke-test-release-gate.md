# 0023. Live Smoke Test as Release Gate

**Status:** Accepted
**Date:** 2026-06-01 (updated 2026-06-07)

## Context

Unit and integration tests verify individual components but cannot catch regressions in the full sync pipeline (content preparation → API upload → Confluence page structure). A real Confluence write path test is needed before each release.

## Decision

A live smoke test is a mandatory release gate, run via `make smoke` (L4).

Each run uses `SmokeProvisioner` (`smoke_provision.py`) to create an **ephemeral private space** (`CS{run_id}`), sync the committed fixture, verify results, and delete the space on teardown. A `smoke-session.json` file in `~/.local/confluence-sync/` survives crashes so `make smoke` EXIT traps and `make release-preflight` can call `smoke reset`.

The smoke sequence (`confluence-sync smoke run -d smoke-live`):

1. **provision** — create ephemeral space (or fallback root page in `CONFLUENCE_SMOKE_FALLBACK_SPACE` / `CONFLUENCE_SPACE`)
2. **clean sync** — sync `tests/live_smoke/fixture/` to the workspace; expect 0 errors
3. **verify** — API assertions: page count, Mermaid PNG attachment, image attachments (`test.png`, `hero.jpeg`), cross-page anchor links (`anchors-source.md` → `#my-section` on `anchors-target.md`)
4. **incremental** — second sync with no file changes; expect all skipped (link normalization may require a second pass)
5. **patch sync** — modify `docs/sibling.md`; expect exactly 1 updated
6. **teardown** — delete ephemeral space; clear `smoke-session.json`

Configuration:

- `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env` (required for live smoke)
- `tests/live_smoke/confluence-sync.yml` — destination `smoke-live`
- Optional fallback: `CONFLUENCE_SMOKE_FALLBACK_SPACE` or `CONFLUENCE_SPACE`
- `SMOKE_FORCE_FALLBACK=1` or `make smoke-fallback` — skip private space creation and exercise the fallback path

Release preflight binds smoke success to the current commit: `~/.local/confluence-sync/smoke-last-pass` stores JSON `{"timestamp", "sha"}`. Preflight verifies SHA matches `git rev-parse HEAD` and timestamp is within 7 days.

If `CONFLUENCE_TOKEN` is not set, live smoke fails with a clear error (not silently skipped in maintainer workflows).

## Consequences

- Live smoke is required before tagging a release
- `make release-rehearsal` (L5) runs the full release script except version bump/tag
- The fixture is versioned in the repo — regressions are reproducible
- No manual `CONFLUENCE_SMOKE_ROOT_PAGE_ID` or CSYNC space setup
