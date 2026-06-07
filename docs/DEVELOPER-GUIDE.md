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

### 6.1 Prerequisites

Ensure you have the following tools installed on your development machine:
- **Python**: `3.11`, `3.12`, or `3.13` (recommended: `3.13`).
- **Git**: Installed and configured.
- **Node.js & npm**: Required if rendering Mermaid diagrams locally during tests.
  - Setup: `npm install -g @mermaid-js/mermaid-cli`
- **Homebrew**: Required to run the local package/formula integration tests (`brew test`).
- **Nox**: (Optional) Highly recommended to run multi-version testing. Install with: `pip install nox`.

### 6.2 Initial Environment Setup

Follow these steps to clone the repository and configure your isolated local development environment:

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/zeta-oss/confluence-sync.git
   cd confluence-sync
   ```

2. **Run Dev Bootstrap**:
   You can either run the bootstrap script directly or use the `make install` shortcut:
   ```bash
   make install
   # This executes `./scripts/bootstrap-dev.sh` under the hood, which:
   # - Creates a local Python virtual environment `.venv/`
   # - Installs the package in editable mode with development dependencies: `pip install -e .[dev]`
   ```

3. **Activate the Virtual Environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Verify the Installation**:
   Verify that your local `confluence-sync` package is accessible and points to your working directory:
   ```bash
   which confluence-sync
   confluence-sync --version
   ```

### 6.3 Atlassian Credentials Configuration

To run live smoke tests (`make smoke`, `make smoke-fallback`, etc.), you must configure credentials to authenticate with your Atlassian Confluence instance:

1. **Generate an API Token**:
   - Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
   - Click **Create API token**, give it a name (e.g., `confluence-sync-dev`), and copy the token.

2. **Create the Local Credentials File**:
   Store the token in the dedicated global user directory. This is excluded from git repositories to prevent accidental leakage:
   ```bash
   mkdir -p ~/.local/confluence-sync
   cat <<EOF >> ~/.local/confluence-sync/.env
   CONFLUENCE_TOKEN=your_atlassian_api_token_here
   EOF
   ```
   *Note: If your Confluence Cloud organization restricts ephemeral space creation, you can also add your personal or designated space as a fallback:*
   ```bash
   echo "CONFLUENCE_SMOKE_FALLBACK_SPACE=your_personal_space_key" >> ~/.local/confluence-sync/.env
   ```

---

## 7. Testing strategy

We utilize a comprehensive **six-layer testing hierarchy** to catch regressions at every phase, ranging from fast, offline unit checks to full live execution on consumer repositories. This strategy is fully documented in [E2E-TEST-PLAN.md](E2E-TEST-PLAN.md).

| Layer | Name | Command | Description | Needs Token? |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | Unit + CLI | `make test` | Fast offline pytest suite + CLI arg/subprocess tests | No |
| **L2** | Shell Integration | `make test-scripts` | Validates helper functions, traps, and preflight gates | No |
| **L3** | Pipeline | `make test-pipeline` | Mocked HTTP pipeline checking end-to-end sync logic | No |
| **L4** | Live Smoke | `make smoke` | Real Confluence lifecycle (ephemeral space sync & verify) | Yes |
| **L4** | Fallback Smoke | `make smoke-fallback` | Tests the fallback path using a pre-existing space | Yes |
| **L5** | Release Rehearsal | `make release-rehearsal` | Full dry-run release simulation (dist/brew/checks) | Yes |
| **L6** | Consumer Validation | `make verify-consumers` | Syncs actual production documents in dry-run mode | Yes |

To run all offline checks (L1, L2, L3) at once, use the combined shortcut:
```bash
make test-all
```

### 7.1 Detailed Testing Instructions

#### Running L1, L2, L3 (Offline)
These tests require no credentials or internet connection, making them ideal to run on every commit or file save.
```bash
# Run standard unit tests and CLI tests
make test

# Run script-level validation tests
make test-scripts

# Run mocked sync pipeline integration tests
make test-pipeline

# Run all linting and static analysis (ruff)
make lint
```

#### Running L4 Live Smoke (`make smoke`)
Live smoke tests verify actual interaction with Confluence Cloud:
- **Ephemeral Space Mode**: The test automatically provisions a temporary space (`CS<unique-id>`), uploads media files, creates and updates pages, asserts that relative cross-links and cross-page anchor links render correctly, and then cleanly deletes the space on completion or crash (via an `EXIT` signal trap).
- **Space-restricted Fallback Mode**: If your Atlassian user does not have permission to create spaces, use `make smoke-fallback`. This will utilize your fallback space configured in `.env`, using run-unique page prefixes (e.g. `CSYNC-Smoke-Root-<id>`) to avoid page collisions, and cleanly deletes its sub-tree on termination.

```bash
# Ephemeral space run (recommended)
make smoke

# Fallback space run (restricted environments)
make smoke-fallback
```

#### Running L5 Release Rehearsal (`make release-rehearsal`)
Crucial to run before any production release. This simulates the exact release process (building sdist, updating Homebrew Formula, installing from a temporary local tap, and running `brew test`) without making any git commits or tags:
```bash
make release-rehearsal
```

#### Running L6 Consumer Validation (`make verify-consumers`)
Validates that the current codebase is 100% backward compatible and runs successfully against massive, real-world consumer documentation structures (`zeta-ai-product-strategy` and `writing-work` repositories):
```bash
make verify-consumers
```

### 7.2 Safety & Cleanup Guarantees

- **No Home Pollution**: The test suite patches `HOME` and `project_root` to run in isolated `pytest` temporary paths. It will never mutate your real local files or real state directories during unit/integration tests.
- **Leak Prevention**: Both `make smoke` and `make release-rehearsal` register `EXIT` traps. If a test run is cancelled or crashes mid-way, the temporary Confluence space/pages are automatically wiped from Atlassian. Check that no `smoke-session.json` remains in `~/.local/confluence-sync/` after runs.

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
