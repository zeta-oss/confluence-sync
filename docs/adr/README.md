# Architecture Decision Records

ADRs document **why** the tool is shaped the way it is. They are first-class documentation for contributors and for future refactors.

## Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ Accepted | Active, in force |
| ⚠️ Superseded | Replaced by a later ADR |
| 📋 Proposed | Under discussion |
| ❌ Rejected | Considered but not adopted |

## How to add an ADR

1. Copy `template.md` → `docs/adr/NNNN-short-title.md`
2. Set status to `Proposed`
3. Fill in Context, Decision, Consequences
4. When merged: update status to `Accepted`
5. Update this index

## Index

### Migrated (from `_confluence_sync/decisions/`) — 0001–0014

| ID | Title | Status |
|----|-------|--------|
| [0001](0001-two-phase-sync-architecture.md) | Two-phase sync architecture | ✅ Accepted |
| [0002](0002-module-separation.md) | Module separation (preparer vs API client) | ✅ Accepted |
| [0003](0003-data-directory-structure.md) | Data directory under tool install | ⚠️ Superseded by [0016](0016-project-local-config-directory.md) |
| [0004](0004-content-hash-change-detection.md) | Content hash change detection | ✅ Accepted |
| [0005](0005-jsonl-format-sync-state.md) | JSONL sync state | ✅ Accepted |
| [0006](0006-destination-based-architecture.md) | Destination-based configuration | ✅ Accepted |
| [0007](0007-file-path-only-lookup-title-suffix.md) | File path lookup + title suffix | ⚠️ Superseded by [0010](0010-remove-title-suffixing.md) |
| [0008](0008-migrate-to-rest-api-v2.md) | REST API v2 | ✅ Accepted |
| [0009](0009-use-native-confluence-folders.md) | Native Confluence folders | ✅ Accepted |
| [0010](0010-remove-title-suffixing.md) | Remove title suffixing | ✅ Accepted |
| [0011](0011-readme-as-separate-pages.md) | README as separate pages | ✅ Accepted |
| [0012](0012-confluence-title-mapping-files.md) | Title mapping files (no auto-disambiguation) | ✅ Accepted |
| [0013](0013-parallel-folder-sync.md) | Parallel folder sync + sync state trust | ✅ Accepted |
| [0014](0014-env-file-wrapper.md) | `run-sync-with-env.py` wrapper | ⚠️ Superseded by [0020](0020-user-local-env-loading.md) |

### New (packaging refactor) — 0015–0028

| ID | Title | Status |
|----|-------|--------|
| [0015](0015-standalone-package.md) | Standalone `confluence-sync` package | ✅ Accepted |
| [0016](0016-project-local-config-directory.md) | Project-local `.confluence-sync/` layout | ✅ Accepted |
| [0017](0017-config-file-discovery.md) | Config file discovery precedence | ✅ Accepted |
| [0018](0018-state-directory-layout.md) | State directory layout | ✅ Accepted |
| [0019](0019-git-metadata-per-file-resolution.md) | Per-source `git_root` for metadata | ✅ Accepted |
| [0020](0020-user-local-env-loading.md) | User-local `.env` loading (supersedes ADR 0014) | ✅ Accepted |
| [0021](0021-hatchling-build-backend.md) | Hatchling as build backend | ✅ Accepted |
| [0022](0022-nox-task-runner.md) | Nox as task runner | ✅ Accepted |
| [0023](0023-live-smoke-test-release-gate.md) | Live smoke test release gate | ✅ Accepted |
| [0024](0024-test-cleanup-policy.md) | Test and smoke cleanup policy | ✅ Accepted |
| [0025](0025-argparse-over-click.md) | Argparse over Click for CLI | ✅ Accepted |
| [0026](0026-homebrew-distribution.md) | Homebrew distribution (in-repo formula) | ✅ Accepted |
| [0027](0027-consumer-migration-strategy.md) | Consumer migration strategy | ✅ Accepted |
| [0028](0028-writing-work-repo-independence.md) | Writing-work repo independence | ✅ Accepted |
