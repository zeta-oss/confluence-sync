# 0023. Live Smoke Test as Release Gate

**Status:** Accepted
**Date:** 2026-06-01

## Context

Unit and integration tests verify individual components but cannot catch regressions in the full sync pipeline (content preparation → API upload → Confluence page structure). A real Confluence write path test is needed before each release.

## Decision

A live smoke test is a mandatory release gate, run via `nox -s live_smoke` (or `make smoke`).

The smoke test:
1. **reset** — clean up any existing smoke test pages in Confluence
2. **run** — sync `tests/live_smoke/fixture/` to a dedicated Confluence page under `CONFLUENCE_SMOKE_ROOT_PAGE_ID`
3. **verify** — call Confluence API and assert: page count, Mermaid PNG attachments, image attachments, link integrity

`tests/live_smoke/fixture/` contains:
- Pages with internal cross-links
- A Mermaid diagram block
- A local image reference

Configuration via env vars:
- `CONFLUENCE_TOKEN`
- `CONFLUENCE_USERNAME`
- `CONFLUENCE_SMOKE_ROOT_PAGE_ID`

If `CONFLUENCE_TOKEN` is not set, `live_smoke` is skipped (not failed) in unit test runs.

## Consequences

- Live smoke is required before tagging a release
- Smoke test has its own cleanup logic to avoid Confluence pollution
- The fixture is versioned in the repo — regressions are reproducible
