# Release Guide

Maintainer-only. Automated steps run via `make release VERSION=x.y.z`
(calls `scripts/release.sh`).

## Before you release

**Run live smoke first.** Release will fail at preflight without a recent pass.

```bash
make install          # once per machine
make test             # unit + CLI tests
make smoke            # live Confluence smoke (creates + destroys ephemeral space)
make release-preflight  # optional: verify prerequisites without bumping version
make release VERSION=x.y.z
```

`make smoke` records a timestamp at `~/.local/confluence-sync/smoke-last-pass`.
`make release` requires that file to be present and younger than 7 days
(override with `SMOKE_GATE_MAX_AGE_HOURS=168`).

## Prerequisites

- On `main` branch, clean working tree
- `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env`
- `CONFLUENCE_SPACE` in the same file (fallback if ephemeral space creation is denied)
- `mmdc` (mermaid-cli) on PATH, or `npx @mermaid-js/mermaid-cli`
- Dev venv: `make install` (no global `nox` required)
- `brew` (Homebrew) installed for formula test
- GitHub CLI `gh` installed (optional, for creating the release)

## Automated release steps (`scripts/release.sh VERSION`)

| Step | What happens |
|------|-------------|
| 1 | Verify clean git status on `main` |
| 2 | `make release-preflight` — token, mmdc, brew, doctor, recent `make smoke` |
| 3 | Bump version in `pyproject.toml` + `__init__.py`; update `CHANGELOG.md` |
| 4 | `make test` — unit + integration + CLI tests + coverage gate |
| 5 | Require `mmdc` on PATH (Mermaid gate) |
| 6 | Register `trap EXIT` → `confluence-sync smoke reset -d smoke-live` |
| 7 | `make smoke` — full clean + incremental + media smoke (ephemeral space) |
| 8 | `hatch build` — wheel + sdist |
| 9 | `./scripts/publish-brew.sh VERSION` — update Formula `url` + `sha256` |
| 10 | `brew test --formula Formula/confluence-sync.rb` |
| 11 | Commit `chore(release): vX.Y.Z` + tag `vX.Y.Z` |

## Live smoke

Smoke tests auto-provision an ephemeral private Confluence space per run and
delete it on teardown. No manual CSYNC space setup is required. See
`tests/live_smoke/README.md`.

## Manual steps (after push)

1. `git push && git push --tags`
2. `gh release create vX.Y.Z dist/*` (optional GitHub release)
3. On a second machine: `brew update && brew upgrade confluence-sync`
4. Consumer dry-run: `confluence-sync sync -d foundry-cto --dry-run --project-root ~/Git/zeta-ai-product-strategy`

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
