# User Guide

> **Warning:** `confluence-sync` is a **one-way** sync (Markdown → Confluence).
> Any edits made directly in Confluence will be overwritten on the next sync.

## 1. Introduction

`confluence-sync` reads Markdown files from a Git repository and creates or updates the corresponding pages in Confluence, preserving the folder hierarchy as Confluence folders.

**Key concepts:**
- **Destination** — a named sync target (Confluence space + root page + source folders)
- **Source folder** — a directory of Markdown files, relative to the project root
- **Project root** — the directory containing `.git/`
- **Sync state** — a local JSONL file recording page IDs; enables incremental updates

## 2. Installation

### Homebrew (recommended)

```bash
brew tap zeta-oss/confluence-sync https://github.com/zeta-oss/confluence-sync.git
brew install confluence-sync
```

### From source

```bash
pip install git+https://github.com/zeta-oss/confluence-sync.git
# or: pip install -e . (from a clone)
```

### System dependencies

- **git** (required)
- **Node `@mermaid-js/mermaid-cli`** (optional, for Mermaid diagram rendering):
  ```bash
  npm install -g @mermaid-js/mermaid-cli
  ```

Verify: `confluence-sync --version` and `confluence-sync doctor`

## 3. Authentication

Create an [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) and store it:

```bash
mkdir -p ~/.local/confluence-sync
echo 'CONFLUENCE_TOKEN=your-token-here' >> ~/.local/confluence-sync/.env
```

**Never** put tokens in `confluence-sync.yml`. The `.env` file is loaded automatically before each sync.

## 4. First-time setup

```bash
cd ~/Git/my-docs-repo       # must contain .git/
confluence-sync init         # creates .confluence-sync/confluence-sync.yml
# Edit .confluence-sync/confluence-sync.yml (see section 5)
confluence-sync doctor -d my-destination
confluence-sync sync -d my-destination
```

`init` also creates `.confluence-sync/.gitignore` which ignores the `destinations/` state directory.

## 5. Configuration reference

Config file: `.confluence-sync/confluence-sync.yml` (or `~/.local/confluence-sync/confluence-sync.yml` as global fallback).

See [`examples/confluence-sync.yml`](../examples/confluence-sync.yml) for an annotated template.

### Discovery order

| Priority | Path |
|----------|------|
| 1 | `--config PATH` (explicit) |
| 2 | `{project-root}/.confluence-sync/confluence-sync.yml` |
| 3 | `~/.local/confluence-sync/confluence-sync.yml` |

### Key fields

| Field | Required | Description |
|-------|----------|-------------|
| `destinations[].id` | Yes | Unique identifier used with `-d` flag |
| `destinations[].confluence.url` | Yes | `https://your-org.atlassian.net` |
| `destinations[].confluence.space_key` | Yes | Confluence space key |
| `destinations[].confluence.root_page_title` | Yes | Title of the root page under which to sync |
| `destinations[].confluence.root_page_id` | No | Pin to a specific page ID (avoids creating a duplicate root) |
| `destinations[].source.folders[].path` | Yes | Path relative to project root |
| `destinations[].source.folders[].create_root_parent` | No | Create a folder page for the source folder (default: true) |
| `destinations[].source.folders[].title` | No | Custom folder title |
| `destinations[].credentials.username` | Yes | Atlassian email |
| `destinations[].credentials.token_env_var` | Yes | Name of the env var holding the token |
| `destinations[].options.add_git_metadata` | No | Add git commit footer (default: false) |
| `destinations[].options.parallel_threads` | No | Parallelism 1–50 (default: 5) |
| `destinations[].options.dry_run` | No | Dry-run by default (default: false) |

## 6. Running sync

```bash
# Sync a single destination
confluence-sync sync -d my-destination

# Sync all destinations
confluence-sync sync --all

# Dry-run (prepare + validate; no API writes)
confluence-sync sync -d my-destination --dry-run

# Force update all pages (ignore content-hash skip)
confluence-sync sync -d my-destination --force-update

# Partial sync (only a subfolder)
confluence-sync sync -d my-destination --folder docs/getting-started

# Override project root
confluence-sync sync -d my-destination --project-root ~/Git/other-repo
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Configuration or usage error |
| 2 | Sync completed but some pages had errors |

## 7. Project layout after init

```
my-docs-repo/
├── .git/
├── docs/                         ← your Markdown
├── .confluence-sync/
│   ├── confluence-sync.yml       ← config (commit this)
│   ├── .gitignore                ← ignores destinations/
│   └── destinations/{id}/        ← sync state (gitignored)
│       ├── sync-state.jsonl
│       ├── sync-metadata.json
│       └── sync-report-*.md
└── .confluence-mapping.yaml      ← optional title overrides
```

## 8. Page titles and `.confluence-mapping.yaml`

By default, the page title is the first `# Heading` in the Markdown file. To override, create `.confluence-mapping.yaml` in any directory:

```yaml
pages:
  my-file.md: "Custom Page Title"
folders:
  my-folder: "Custom Folder Title"
folder_title: "Title for This Folder"
```

**Important:** Title conflicts are not auto-resolved (see [ADR 0012](adr/0012-confluence-title-mapping-files.md)). Use `.confluence-mapping.yaml` to assign unique titles.

## 9. Features

- **Folder hierarchy** → Confluence folders/pages
- **README.md** in a folder becomes a separate page (ADR 0011)
- **Cross-link conversion** — relative `.md` links and anchor links are converted to native Confluence links.
  - **Pre-scan Title Mapping**: Prior to content preparation, `confluence-sync` automatically pre-scans all Markdown files in your directory to build a local map of file-to-title mapping. This ensures that cross-page relative and anchor links can be fully resolved *even on a clean sync* when Confluence page IDs are not yet registered.
  - **Fabric-safe Fallback Mode**: If `confluence_base_url` is configured in your config, pages will link directly to secure Confluence page ID urls (Fabric-safe links). On a clean sync where page IDs are not yet known, the tool gracefully falls back to Confluence macro `ac:link` format, promoting them to direct page ID links on the next incremental sync.
- **Git metadata footer** — "Last updated · commit hash · View on GitHub"
- **Mermaid → PNG** — ` ```mermaid ` blocks rendered to PNG and uploaded as attachments
- **Local images** → Confluence attachments
- **`.confluence-ignore`** — gitignore-style exclusion patterns
- **Orphan deletion** — pages removed from Git are deleted from Confluence

## 10. Sync reports

After each sync, a report is saved to `.confluence-sync/destinations/{id}/sync-report-{timestamp}.md`.

Statuses: `created` (new page), `updated` (content changed), `skipped` (unchanged), `error`.

Use `--force-update` to re-sync all pages regardless of content hash (useful after Confluence edits that were overwritten).

## 11. Troubleshooting

| Problem | Solution |
|---------|----------|
| 401 Unauthorized | Check `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env` |
| "Not inside a Git repository" | `cd` into a repo with `.git/` or use `--project-root` |
| Title conflict error | Add `.confluence-mapping.yaml` with unique title for conflicting page |
| Mermaid diagrams blank | Install `@mermaid-js/mermaid-cli`: `npm install -g @mermaid-js/mermaid-cli` |
| Root page conflict (TDA pattern) | Set `root_page_id` in config to pin to the existing space homepage |
| Wrong GitHub URL in footer | Set `options.github_repo_override` to the correct HTTPS URL |

Run `confluence-sync doctor` for a full pre-flight check.

## 12. Migration from `_confluence_sync`

See [docs/MIGRATION.md](MIGRATION.md).

## 13. FAQ

**Can I edit pages in Confluence?** No — edits are overwritten on next sync. This is by design.

**Can I sync only one subfolder?** Yes: `confluence-sync sync -d DEST --folder path/to/subfolder`

**Where does config live without a project config?** Falls back to `~/.local/confluence-sync/confluence-sync.yml`.

**How do I uninstall?** `brew uninstall confluence-sync` (or `pip uninstall confluence-sync`).
