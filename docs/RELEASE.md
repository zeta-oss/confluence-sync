# Release Guide

Maintainer-only. Automated steps run via `make release VERSION=x.y.z`
(calls `scripts/release.sh`).

## Prerequisites

- On `main` branch, clean working tree
- `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env`
- `mmdc` (mermaid-cli) on PATH: `npm install -g @mermaid-js/mermaid-cli`
- `nox` installed: `pip install nox`
- `brew` (Homebrew) installed for formula test
- GitHub CLI `gh` installed (optional, for creating the release)

## Automated release steps (`scripts/release.sh VERSION`)

| Step | What happens |
|------|-------------|
| 1 | Verify clean git status on `main` |
| 2 | Bump version in `pyproject.toml` + `__init__.py`; update `CHANGELOG.md` |
| 3 | `nox -s test cli` — unit + integration + CLI subprocess tests + coverage ≥75% |
| 4 | Require `mmdc` on PATH (Mermaid gate) |
| 5 | Register `trap EXIT` → `confluence-sync smoke reset -d smoke-live` |
| 6 | `nox -s live_smoke` — full clean + incremental + media + links smoke run |
| 7 | `nox -s build` — wheel + sdist |
| 8 | `./scripts/publish-brew.sh VERSION` — update Formula `url` + `sha256` |
| 9 | `nox -s brew_test` — install formula locally and run test block |
| 10 | Commit `chore(release): vX.Y.Z` + tag `vX.Y.Z` |

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
# Update Formula manually, then re-run: nox -s brew_test
```
