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

---

## 2. Orientation: The Git vs. Confluence Dissonance

When adopting a "Docs-like-Code" approach with `confluence-sync`, engineers and technical writers must recognize a fundamental architectural dissonance between local git-based file systems and the cloud database architecture of Atlassian Confluence. 

Understanding these differences is key to structuring your content effectively and avoiding common sync failures.

### 2.1 Flat vs. Hierarchical Namespace (The Title Collision Problem)

This is the most common point of friction.

*   **In Git / File Systems (Hierarchical Namespace)**:
    File paths are fully scoped by their parent directories. You can organize files like this without any issue:
    ```text
    docs/
    ├── platform/
    │   └── introduction.md       # Scoped as docs/platform/introduction.md
    └── database/
        └── introduction.md       # Scoped as docs/database/introduction.md
    ```
    The filesystem happily allows duplicate file names (`introduction.md`) because their paths are unique.
*   **In Confluence (Flat Namespace)**:
    Within any single Confluence Space, **every single Page Title must be globally unique**. Confluence completely ignores your folder structures and hierarchies when validating titles.
    If you attempt to sync the structure above directly, Confluence will reject the second page with a `400 Bad Request` or `Title already exists` error.
*   **The Solution**: Page titles must be globally unique across your target space. Use descriptive `# Headings` in your Markdown or leverage a local `.confluence-mapping.yaml` file (see Section 9) to explicitly assign unique page titles while retaining comfortable file paths.

### 2.2 Path-Based vs. ID-Based Identity (The Rename Challenge)

*   **In Git**:
    Git identifies content by its directory path. If you rename `docs/old.md` to `docs/new.md`, Git registers a deletion at the old path and a creation at the new path.
*   **In Confluence**:
    Confluence identifies content using an immutable database ID (`pageId`). A page's title is merely a mutable attribute of that ID. 
    If you rename a local file, a naive sync tool would delete the old page in Confluence and create a new one, causing links to break, page history to vanish, and comments to be destroyed.
*   **The Solution**: `confluence-sync` uses a local **Sync State** file (`sync-state.jsonl`) that maps each file key (e.g., `docs/getting-started.md`) to its permanent Confluence `page_id`. This allows the tool to track renames, preserve page IDs, and update titles in-place without losing comments, history, or child attachments.

### 2.3 Structure vs. Content: Native Folder Support

*   **In Git**:
    Directories are pure structural containers. A folder cannot hold text, images, or commit metadata of its own; only files can contain text.
*   **In Confluence**:
    Historically, Confluence had no native "folder" concept—directories had to be represented as regular Page nodes, meaning structural directories and content pages competed for names and namespaces.
    Modern Confluence Cloud REST API v2 introduces **Native Folder Support** (`/wiki/api/v2/folders`). Native Folders are structural-only containers with absolutely no body content.
*   **The Solution**: `confluence-sync` leverages REST API v2 to create native folders for your local subdirectories. 
    - Folders are kept completely separate from pages.
    - Because folders are structure-only, they have no text body. If you have a `README.md` or `index.md` inside a local subdirectory, `confluence-sync` automatically uploads it as a standard **Page nested under that folder**, rather than trying to write content to the folder itself.
    - Directory-level links (like `[Guide](../guides/)`) are automatically parsed and mapped to point to that folder's `README.md` or `index.md` page for maximum convenience.

### 2.4 Separated Folder and Page Namespaces (No Collisions)

*   **The Concept**:
    Because native Folders and Pages are different primitives in Confluence v2, **folders and pages reside in separate namespaces**.
*   **The Benefit**:
    A folder named `setup` will **never** collide with a page named `setup`. They can happily co-exist within the same parent or space, entirely resolving title collision bugs between structure and content.
*   **The Constraint**:
    Folders can also co-exist with the same title under different parent folders. However, under the *same* parent, folder titles must be unique. `confluence-sync` tracks folders separately in its sync state to ensure we always bind child pages to the correct, intended folder parent ID. Use `.confluence-mapping.yaml` to override any folder titles if customization is required.

### 2.5 Markdown Links: Supported Formats & Constraints

While `confluence-sync` performs extensive HTML parsing and link rewriting, not all Markdown link formats can be parsed or resolved cleanly into Confluence macros.

*   **Supported Formats (Highly Robust)**:
    - **Relative files**: `[Guide](../guides/usage.md)`
    - **Relative files with local anchors**: `[Installation](../setup.md#installation-steps)`
    - **Directory links**: `[Parent](../platform/)` (resolves automatically to that folder's `README.md` / `index.md` if present).
    - **Standard web links**: `[Google](https://google.com)` (kept as-is).
*   **Unsupported/Partially Broken Formats**:
    - **Extension-less relative links**: `[Setup](../setup)` — `confluence-sync` relies on the `.md` extension to identify and map the file in the local title pre-scan cache. Excluding `.md` will cause the sync to treat it as an external relative URL and render a broken link.
    - **Absolute local filesystem paths**: `[Doc](/Users/username/docs/usage.md)` or `[Doc](C:\docs\usage.md)` — these are ignored to prevent local development path exposure.
    - **Bypassing Markdown with raw HTML anchors**: `<a href="../usage.md">Usage</a>` — raw HTML elements bypassing standard Markdown syntax cannot be reliably transformed and may lead to broken URLs in the target.

### 2.6 Media, Image & Attachment Limitations

Images and media referenced in Markdown (`![Alt](./assets/image.png)`) are automatically converted, uploaded to Atlassian as page attachments, and rewritten to Confluence `ac:image` storage tags.

*   **Security Repo Boundary**:
    `confluence-sync` enforces strict repository boundary isolation to prevent security leaks. All referenced asset paths **must reside within the designated `--project-root` boundary**. Any paths trying to walk out of the repository (e.g. `![Leak](../../../private-keys/credentials.png)`) will be blocked and ignored by the sync preparer.
*   **Multimedia Limitations**:
    - **Atlassian Upload Size Limits**: Very large assets (typically >10MB, depending on your organization's Confluence attachment size configurations) will be rejected by Atlassian with a `413 Payload Too Large` error, failing that page's sync.
    - **Video/Audio & Binary Documents**: While standard image formats (`.png`, `.jpeg`, `.jpg`, `.gif`, `.svg`, `.webp`) are embedded cleanly, other rich documents (like `.pdf`, `.mp4`, `.zip` etc.) are uploaded to the page's attachments list, but will not render inline in the body. Users must download them from the Confluence attachments menu or insert them using native Confluence macros.

## 3. Installation

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

## 4. Authentication

Create an [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) and store it:

```bash
mkdir -p ~/.local/confluence-sync
echo 'CONFLUENCE_TOKEN=your-token-here' >> ~/.local/confluence-sync/.env
```

**Never** put tokens in `confluence-sync.yml`. The `.env` file is loaded automatically before each sync.

## 5. First-time setup

```bash
cd ~/Git/my-docs-repo       # must contain .git/
confluence-sync init         # creates .confluence-sync/confluence-sync.yml
# Edit .confluence-sync/confluence-sync.yml (see section 6)
confluence-sync doctor -d my-destination
confluence-sync sync -d my-destination
```

`init` also creates `.confluence-sync/.gitignore` which ignores the `destinations/` state directory.

## 6. Configuration reference

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

## 7. Running sync

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

## 8. Project layout after init

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

## 9. Page titles and `.confluence-mapping.yaml`

By default, the page title is the first `# Heading` in the Markdown file. To override, create `.confluence-mapping.yaml` in any directory:

```yaml
pages:
  my-file.md: "Custom Page Title"
folders:
  my-folder: "Custom Folder Title"
folder_title: "Title for This Folder"
```

**Important:** Title conflicts are not auto-resolved (see [ADR 0012](adr/0012-confluence-title-mapping-files.md)). Use `.confluence-mapping.yaml` to assign unique titles.

## 10. Features

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

## 11. Sync reports

After each sync, a report is saved to `.confluence-sync/destinations/{id}/sync-report-{timestamp}.md`.

Statuses: `created` (new page), `updated` (content changed), `skipped` (unchanged), `error`.

Use `--force-update` to re-sync all pages regardless of content hash (useful after Confluence edits that were overwritten).

## 12. Troubleshooting

| Problem | Solution |
|---------|----------|
| 401 Unauthorized | Check `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env` |
| "Not inside a Git repository" | `cd` into a repo with `.git/` or use `--project-root` |
| Title conflict error | Add `.confluence-mapping.yaml` with unique title for conflicting page (see Section 2.1). |
| Folder title collision | Native folders support duplicate titles space-wide under different parents, but are restricted under the same parent directory. If folders collide under the same parent, customize titles via `.confluence-mapping.yaml` (see Section 2.4). |
| Cross-page links are broken | Verify that your relative links include the `.md` extension. `[page](../page)` is unsupported; use `[page](../page.md)` (see Section 2.5). |
| Anchors are not working | Confluence Cloud strips standard heading `id` attributes from HTML during API retrieval. The sync verify Fallback check matches heading text, but ensure your links strictly use `#heading-text-slug` formatted lowercase (see Section 2.5). |
| Missing or broken images | Ensure image file paths reside completely *inside* your git repository boundary. Absolute local paths or relative paths walking outside the Git root (e.g., `../../external.png`) are blocked for safety (see Section 2.6). |
| Large image fails to upload | Atlassian restricts attachment uploads (usually max 10MB). Optimize or compress your images before syncing (see Section 2.6). |
| Mermaid diagrams blank | Install `@mermaid-js/mermaid-cli`: `npm install -g @mermaid-js/mermaid-cli` |
| Root page conflict (TDA pattern) | Set `root_page_id` in config to pin to the existing space homepage |
| Wrong GitHub URL in footer | Set `options.github_repo_override` to the correct HTTPS URL |

Run `confluence-sync doctor` for a full pre-flight check.

## 13. Migration from `_confluence_sync`

See [docs/MIGRATION.md](MIGRATION.md).

## 14. FAQ

**Can I edit pages in Confluence?** No — edits are overwritten on next sync. This is by design.

**Can I sync only one subfolder?** Yes: `confluence-sync sync -d DEST --folder path/to/subfolder`

**Where does config live without a project config?** Falls back to `~/.local/confluence-sync/confluence-sync.yml`.

**How do I uninstall?** `brew uninstall confluence-sync` (or `pip uninstall confluence-sync`).
