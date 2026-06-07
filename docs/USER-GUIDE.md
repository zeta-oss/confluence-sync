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

Adopting a "Docs-like-Code" approach with `confluence-sync` introduces a powerful workflow, but it requires engineers and technical writers to understand the fundamental architectural differences between local, git-based filesystems and the database-driven model of Atlassian Confluence Cloud. 

Confluence Cloud operates on strict cloud metadata paradigms that diverge from local folder/file structures. Aligning your documentation layout with these realities will ensure a flawless, error-free sync.

---

### 2.1 Flat vs. Hierarchical Page Namespaces (Title Collisions)

The most frequent point of friction when transitioning from local files to Confluence is the namespace structure.

*   **In Git / Local Filesystems (Hierarchical Namespace)**:
    File paths are fully scoped by their parent directories. This structure is perfectly valid and common:
    ```text
    docs/
    ├── platform/
    │   └── introduction.md       # Unique path: docs/platform/introduction.md
    └── database/
        └── introduction.md       # Unique path: docs/database/introduction.md
    ```
    The filesystem permits duplicate filenames (`introduction.md`) because their paths are distinct.
*   **In Confluence Pages (Flat Space-Wide Namespace)**:
    Within any single Confluence Space, **every Page Title must be globally unique**. Confluence validates page titles globally across the entire space, completely ignoring your nesting or folder structures.
    If you attempt to sync the repository layout above directly, Confluence will reject the creation of the second page with a `400 Bad Request` (Title already exists) error.
*   **The Sync Solution**: Page titles must be distinct space-wide. You can resolve this by using descriptive first headings (`# Headings`) in your Markdown files or by using a local `.confluence-mapping.yaml` file (see Section 9) to map duplicate filenames to distinct, Confluence-friendly titles.

---

### 2.2 Separated Folder and Page Namespaces (No Cross-Primitive Collisions)

Unlike older versions of Confluence, modern Confluence Cloud separates folders from pages.

*   **The Namespace Separation**:
    In Confluence REST API v2, native Folders and Pages exist as separate primitives and reside in **completely separate namespaces**.
*   **The Benefit**:
    A folder named `setup` will **never** collide with a page named `setup`. They can co-exist within the same parent directory or space without causing namespace collisions.
*   **The Constraint**:
    Folders are allowed to have duplicate titles space-wide (for example, you can have a folder named `setup` under `development/` and another folder named `setup` under `production/`). However, folder titles must be unique *under the same parent directory*. `confluence-sync` tracks folder parental structures separately in its sync state to keep child page nesting fully aligned.

---

### 2.3 Path-Based vs. ID-Based Identity (The Rename Challenge)

Tracking the identity of documents during renames and moves is critical to maintaining a healthy wiki.

*   **In Git (Path-Based Identity)**:
    Git identifies file identity by its path. If you rename `docs/old.md` to `docs/new.md`, Git registers a deletion of the old path and a creation of the new path.
*   **In Confluence (ID-Based Identity)**:
    Confluence identifies documents by a permanent database ID (`pageId`). A page's title is simply a mutable attribute of that ID. 
    If a sync tool naively followed Git's path-based deletions and creations during a rename, it would delete the old page in Confluence and create a new one. This would break incoming links, erase the page's revision history, and destroy user comments.
*   **The Sync Solution**: `confluence-sync` maintains a local **Sync State** file (`sync-state.jsonl`) that maps each local file path to its permanent Confluence `page_id`. When you rename a file or move it to a different directory locally, the sync engine detects the change, issues an in-place title update or parent move API call, and preserves your page history, incoming links, and comments completely.

---

### 2.4 Structure vs. Content: Native Folder Support

Representing directory containers in a wiki requires separating structure from actual text content.

*   **In Git**:
    Directories are pure structural containers. A folder cannot hold text, images, or commit metadata of its own; only files can contain text.
*   **In Confluence**:
    Historically, folders were represented as regular pages (directory pages), which led to structural nodes competing with document nodes for titles and namespaces. 
    Modern Confluence Cloud REST API v2 provides **Native Folder Support** (`/wiki/api/v2/folders`). Native folders are structure-only containers that do not support a text body.
*   **The Sync Solution**: `confluence-sync` leverages API v2 to create native folders for your local subdirectories.
    - Folders are kept separate from pages and are used purely for visual nesting.
    - Because native folders cannot hold text, if you place a `README.md` or an `index.md` inside a local subdirectory, the sync engine automatically uploads it as a standard **Page nested under that folder**, rather than trying to write body content directly to the folder container.
    - Relative directory links (such as `[Guide](../guides/)`) are automatically parsed and routed to point to the nested folder's `README.md` or `index.md` page for convenient navigation.

---

### 2.5 Markdown Links: Supported Formats & Constraints

While `confluence-sync` performs extensive HTML parsing and relative link rewriting, certain syntax restrictions apply to guarantee clean URL transformations.

*   **Supported Link Formats (Highly Robust)**:
    - **Relative files**: `[Guide](../guides/usage.md)` (converted to native Confluence links).
    - **Relative files with anchors**: `[Installation](../setup.md#installation-steps)` (converted to Fabric-safe Confluence anchor links).
    - **Relative directories**: `[Parent](../platform/)` (automatically routes to that directory's `README.md` or `index.md` if present).
    - **Standard web links**: `[Google](https://google.com)` (kept as-is).
*   **Unsupported/Restricted Link Formats**:
    - **Extension-less relative links**: `[Setup](../setup)` is unsupported. The title pre-scanner relies on the `.md` extension to map file paths to final Confluence page titles. Excluding the extension prevents local resolution, causing the sync to treat it as a broken external link.
    - **Absolute local filesystem paths**: `[Doc](/Users/username/docs/usage.md)` or `[Doc](C:\docs\usage.md)` are blocked and ignored to prevent local development environment leaks.
    - **Raw HTML anchor tags**: Raw `<a href="../usage.md">Usage</a>` bypasses the Markdown AST parser and cannot be reliably rewritten. Always use standard Markdown link format.

---

### 2.6 Media, Image & Attachment Limitations

Images and media files referenced in your Markdown (`![Alt](./assets/image.png)`) are converted, uploaded to Atlassian as page attachments, and rewritten to Confluence `ac:image` storage tags.

*   **Security Repo Boundary**:
    To prevent data leakage, `confluence-sync` enforces strict directory containment. All referenced assets **must reside within the designated `--project-root` boundary**. Any asset path walking out of the repository (for example, `![Leak](../../../private-keys/credentials.png)`) will be blocked and ignored.
*   **Multimedia Restrictions**:
    - **Upload Size Limits**: Large files (typically $>10\text{ MB}$, governed by your organization's Confluence attachment configurations) will be rejected by Atlassian with a `413 Payload Too Large` error, failing that page's sync.
    - **Inline Rendering**: Standard image formats (`.png`, `.jpeg`, `.jpg`, `.gif`, `.svg`, `.webp`) are embedded and rendered inline. Other binary files (such as `.pdf`, `.mp4`, `.zip`, etc.) are uploaded to the page's attachment list, but cannot render inline. Users can download them from the Confluence attachments list.

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
