# Developer Guide

Audience: contributors, maintainers, and engineers extending or forking the tool.

## 1. Project goals

**Goals:**
- Standalone CLI installable via Homebrew
- Destination-based sync; reliable incremental updates
- Self-contained build/release (no external CI)
- Live smoke before every release
- One-way Markdown → Confluence

**Non-goals (v0.1):**
- Bidirectional sync / Confluence → Git
- External CI (GitHub Actions, etc.)
- Homebrew cask (GUI app)
- Non-Markdown sources

## 2. Repository map

```
src/confluence_sync/     # package
  paths.py               # ALL path resolution (project root, config, state, env)
  config.py              # YAML load + validation
  sync.py                # orchestration (Phase 1 prepare → Phase 2a folders → 2b pages → 3 orphans)
  content_preparer.py    # Markdown → Confluence storage format, links, Mermaid
  confluence_sync.py     # REST client, page/folder CRUD, lookup hierarchy
  sync_state.py          # JSONL state, content hashes, rename detection
  git_utils.py           # commit + GitHub URLs per git root
  ignore_handler.py      # .confluence-ignore pattern matching
  title_mapping.py       # .confluence-mapping.yaml loader
  report_generator.py    # Markdown sync report generation
  attachment_handler.py  # image upload and reference conversion
  orphan_handler.py      # orphan page/folder detection and deletion
  smoke_verify.py        # post-sync API assertions (release gate)
  smoke_cleanup.py       # Confluence subtree delete + local state wipe
  cli.py                 # argparse entry point (routes to commands/)
  commands/
    sync.py              # sync subcommand
    init.py              # init subcommand
    doctor.py            # doctor subcommand
    smoke.py             # smoke reset/run/verify subcommands
tests/
  unit/                  # pytest unit tests (no network)
  integration/           # mocked HTTP end-to-end
  cli/                   # subprocess CLI tests
  live_smoke/            # committed fixture + release-gate tests
Formula/                 # Homebrew formula (in-repo tap)
scripts/                 # bootstrap-dev.sh, release.sh, publish-brew.sh
noxfile.py, Makefile     # task entrypoints
examples/                # sample configs
docs/                    # USER-GUIDE, DEVELOPER-GUIDE, RELEASE, MIGRATION, adr/
```

## 3. Architecture overview

```
CLI (argparse) → commands/ → paths.py (SyncContext)
                           → config.py (load YAML)
                           → sync.py (orchestrator)
                               → content_preparer.py (Phase 1: MD → storage)
                               → confluence_sync.py  (Phase 2: REST calls)
                               → orphan_handler.py   (Phase 3: cleanup)
```

Phases:
1. **Prepare** — scan files, convert Markdown, build link cache (no API calls)
2. **Create folders** — parallelised by depth level (ADR 0013)
3. **Sync pages** — parallelised via `ThreadPoolExecutor` (ADR 0013)
4. **Orphan cleanup** — delete pages removed from Git

`SyncContext` carries `project_root`, `config_path`, `state_dir`, `user_dir` through all phases.

## 4. Design decisions

| Choice | Rationale |
|--------|-----------|
| Project-local `.confluence-sync/` | Config + state travel with content repo |
| Global `~/.local/confluence-sync/` | Token, mermaid cache, fallback config — user-scoped |
| `--project-root` requires `.git` | Explicit content boundary; correct git metadata |
| Page IDs in sync state | Survives renames; see ADR 0013 |
| No auto title disambiguation | Explicit `.confluence-mapping.yaml`; see ADR 0012 |
| Fabric-safe `<a href>` links | `ac:link` unsupported in Fabric editor; see ADR 0026 |
| Mermaid as PNG attachments | Reliable rendering vs macro; see ADR 0027 |
| Hatchling + nox, no CI | Self-contained; maintainer Mac is release environment |
| In-repo Formula | Single repo to tap; `publish-brew.sh` updates SHA256 |
| Live smoke before release | Proves clean + incremental + media + links; see ADR 0023 |

## 5. Key modules

| Module | Responsibility |
|--------|----------------|
| `paths.py` | Config/state/project-root resolution; **change here first** |
| `config.py` | YAML load + validation |
| `sync.py` | Orchestration phases |
| `content_preparer.py` | MD → storage format, links, Mermaid |
| `confluence_sync.py` | REST client, page/folder CRUD |
| `sync_state.py` | JSONL state, content hashes |
| `git_utils.py` | Commit + GitHub URLs per git root (ADR 0019) |
| `smoke_verify.py` | Release verification assertions |
| `smoke_cleanup.py` | Confluence reset + local state wipe |

## 6. Local development

```bash
# Prerequisites: Python 3.11+, git, nox (pip install nox)
git clone https://github.com/zeta-oss/confluence-sync.git
cd confluence-sync
./scripts/bootstrap-dev.sh   # creates .venv/, pip install -e .[dev]
source .venv/bin/activate

make test          # nox -s test cli
make smoke         # needs CONFLUENCE_TOKEN
```

## 7. Testing strategy

| Layer | When | Token | Command |
|-------|------|-------|---------|
| Unit | `make test` | No | `pytest tests/unit/` |
| Integration (mocked) | `make test` | No | `pytest tests/integration/` |
| CLI subprocess | `make test` | No | `pytest tests/cli/` |
| Live smoke | `make release` only | Yes | `confluence-sync smoke run -d smoke-live` |

Coverage gate: ≥75% (`fail_under = 75` in `pyproject.toml`).

**Cleanup policy (ADR 0024):**
- All Git repos and state dirs go in `pytest tmp_path`
- `HOME` is monkeypatched per test — no test touches `~/.local/confluence-sync/`
- Live smoke copies fixture to tmp, never mutates committed files
- Confluence teardown runs in `finally` block (always)

## 8. Adding a feature

1. **Config change** → `config.py` validation + `examples/` + USER-GUIDE section
2. **Confluence API behavior** → `confluence_sync.py` + mocked integration test
3. **Markdown transform** → `content_preparer.py` + unit test
4. **New CLI flag** → `commands/sync.py` + `tests/cli/`
5. **ADR** → `docs/adr/` if architectural; PR description if minor

## 9. Release

See [docs/RELEASE.md](RELEASE.md). Run: `make release VERSION=x.y.z`

Gates: test → live smoke → build → formula bump → brew test → tag.

## 10. Taking the project forward

**Becoming a maintainer:** clone → `./scripts/bootstrap-dev.sh` → read this guide → `make test`

**Backlog ideas:** external link validation; non-image attachments; `fix-broken-links` subcommand; Linux packaging; config schema versioning

**Forking:** package is MIT; tap URL changes; state format documented in Appendix A

---

## Appendices

### A. Sync state JSONL record schema

Each line in `sync-state.jsonl` is a JSON object:

**Page record:**
```json
{
  "file_path": "source-folder/docs/page.md",
  "page_id": "12345678",
  "page_title": "Page Title",
  "page_title_original": "Page Title",
  "last_sync_commit": "abc1234",
  "last_sync_date": "2025-01-01T12:00:00Z",
  "last_sync_status": "created",
  "content_hash": "sha256hex...",
  "version": 3,
  "parent_id": "87654321",
  "content_signature": "16hexchars"
}
```

**Folder record:**
```json
{
  "type": "folder",
  "folder_path": "source-folder/docs/sub",
  "folder_id": "99999",
  "folder_title": "Sub",
  "parent_id": "87654321",
  "status": "created",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

The latest record per path wins (JSONL is append-only; `compact_sync_state` deduplicates).

### B. Confluence API version

Uses Confluence REST API v2 (`/wiki/api/v2/`). Native folders (`/folders` endpoint) are used where available. See ADR 0008 and ADR 0009.

### C. ADR index

→ [`docs/adr/README.md`](adr/README.md)

### D. Glossary

| Term | Definition |
|------|-----------|
| **destination** | A named sync target: one Confluence root page + one or more source folders |
| **file_key** | The relative path used as the unique key in sync state: `{source_folder}/{rel_path}` |
| **content_hash** | SHA-256 of the prepared Confluence storage format; used for change detection |
| **root_page_id** | The Confluence page ID of the root page under which content is synced |
| **state_dir** | Base directory for all destination state: `.confluence-sync/destinations/` |
