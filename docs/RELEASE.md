# Release Guide

Maintainer-only. Automated steps run via `make release VERSION=x.y.z`
(calls `scripts/release.sh`).

## Before you release

**Run live smoke and release rehearsal first.** Release will fail at preflight
without a recent smoke pass bound to the current commit.

```bash
make install              # once per machine
make test-all             # L1 + L2 + L3 (unit, scripts, pipeline)
make smoke                # L4 — live Confluence smoke (creates + destroys ephemeral space)
make release-rehearsal    # L5 — full release dry-run (no version bump/tag)
make release-preflight    # optional: verify prerequisites without bumping version
make release VERSION=x.y.z
```

`make smoke` records JSON at `~/.local/confluence-sync/smoke-last-pass`:

```json
{"timestamp": "2026-06-07T13:00:00Z", "sha": "<git rev-parse HEAD>"}
```

`make release-preflight` requires that file, verifies `sha` matches `git rev-parse HEAD`,
and checks `timestamp` is younger than 7 days (`SMOKE_GATE_MAX_AGE_HOURS=168`).

For doc-only changes after smoke on a prior commit, you may set
`SMOKE_GATE_ALLOW_STALE_SHA=1` (use sparingly). Legacy plain-timestamp files
fail with “Re-run: make smoke”.

## Definition of Done — ready to tag vX.Y.Z

- [ ] `make test-all` green on `main`
- [ ] `make smoke` green; `smoke-last-pass` SHA == `git rev-parse HEAD`
- [ ] `make release-rehearsal` green
- [ ] No `smoke-session.json` left in `~/.local/confluence-sync/`
- [ ] No orphan `CS*` spaces in Confluence admin
- [ ] CHANGELOG `[Unreleased]` section complete
- [ ] `make release VERSION=x.y.z` completes step 11
- [ ] Post-push: `make verify-consumers` passes

See [E2E-TEST-PLAN.md](E2E-TEST-PLAN.md) for the full six-layer testing strategy.

## Prerequisites

- On `main` branch, clean working tree
- `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env`
- `CONFLUENCE_SPACE` or `CONFLUENCE_SMOKE_FALLBACK_SPACE` in the same file (fallback if ephemeral space creation is denied)
- `mmdc` (mermaid-cli) on PATH, or `npx @mermaid-js/mermaid-cli`
- Dev venv: `make install` (no global `nox` required)
- `brew` (Homebrew) installed for formula test
- GitHub CLI `gh` installed (optional, for creating the release)

## Automated release steps (`scripts/release.sh VERSION`)

| Step | What happens |
|------|-------------|
| 1 | Verify clean git status on `main` |
| 2 | `make release-preflight` — token, mmdc, brew, doctor, recent `make smoke` + SHA gate |
| 3 | Bump version in `pyproject.toml` + `__init__.py`; update `CHANGELOG.md` |
| 4 | `make test` — unit + integration + CLI tests + coverage gate |
| 5 | Require `mmdc` on PATH (Mermaid gate) |
| 6 | Register `trap EXIT` → `confluence-sync smoke reset -d smoke-live` |
| 7 | `make smoke` — full clean + incremental + media smoke (ephemeral space) |
| 8 | `hatch build` — wheel + sdist |
| 9 | `./scripts/publish-brew.sh VERSION` — update Formula `url` + `sha256` |
| 10 | `brew test --formula Formula/confluence-sync.rb` |
| 11 | Commit `chore(release): vX.Y.Z` + tag `vX.Y.Z` |

## Release rehearsal (L5)

`make release-rehearsal` runs steps 1–8 and 10 of the release workflow **without**
bumping version, committing, or tagging. Uses `REHEARSAL_VERSION=99.0.0-rehearsal`
for the local Homebrew formula SHA check. Mandatory once per release candidate on
the same machine that will run `make release`.

## Live smoke

Smoke tests auto-provision an ephemeral private Confluence space per run and
delete it on teardown. No manual CSYNC space setup is required. See
`tests/live_smoke/README.md`.

Use `make smoke-fallback` (or `SMOKE_FORCE_FALLBACK=1 make smoke`) to exercise the
personal-space + run-unique titles fallback path when space creation is denied.

## Manual steps (after push)

1. `git push && git push --tags`
2. `gh release create vX.Y.Z dist/*` (optional GitHub release)
3. On a second machine: `brew update && brew upgrade confluence-sync`
4. `make verify-consumers` — dry-run sync in consumer repos (L6)

## Rollback

If the release commit has been pushed but not yet consumed:

```bash
git tag -d vX.Y.Z
git push origin :vX.Y.Z
git revert HEAD  # undo chore(release) commit
```

## Formula SHA256 troubleshooting

If `publish-brew.sh` fails (GitHub archive not yet available):

```bash
# Download archive locally, compute sha
curl -sL https://github.com/zeta-oss/confluence-sync/archive/refs/tags/vX.Y.Z.tar.gz \
  | shasum -a 256
# Update Formula manually, then re-run: brew test --formula Formula/confluence-sync.rb
```
