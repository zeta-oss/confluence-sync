# Writing in Markdown, Publishing to Confluence

## The Author's Problem

Anyone who writes documentation for a living—or as a significant part of their job—knows the friction. Product requirements, operational playbooks, strategy briefs, role charters, training material: the writing itself is hard enough. The tooling should not add to it.

Rich-text wiki editors ask authors to compose in a browser, format by hand, and manage page structure click by click. That workflow made sense when the editor was also the publishing destination. It makes less sense now, because the most productive writing environment has quietly shifted elsewhere: plain Markdown files, edited locally, increasingly with an AI assistant alongside.

This post makes a simple argument: author in Markdown, let AI carry part of the drafting load, and treat publishing to Confluence as an automated last step rather than a manual chore. [`confluence-sync`](https://github.com/zeta-oss/confluence-sync) is a small open-source CLI that handles that last step.

---

## Why Markdown Is Where the Productivity Is

### AI assistants work best in plain text

Markdown is, in practice, the native output format of large language models. Ask an AI assistant to draft a role charter, restructure a requirements document, or synthesize a long discussion into a brief, and what comes back is well-formed Markdown. The format's simple semantics—headings, lists, tables, code blocks—are exactly the structure LLMs handle reliably.

This matters for authors in a concrete way: a first draft that used to take an afternoon can be generated, reviewed, and reshaped in minutes. The author's time shifts from typing and formatting to judgment—deciding what is right, what is missing, and what to cut. Revisions work the same way: when the underlying facts change, an assistant can propose the corresponding documentation update, and the author reviews a diff instead of rewriting pages.

None of this works nearly as well inside a WYSIWYG editor. Plain text is what makes the AI collaboration loop cheap and fast.

### The format is versatile beyond the AI story

The productivity gain is the headline, but Markdown brings quieter benefits that compound over time:

* **Version control.** Markdown files live naturally in Git. Documents get history, diffs, branches, and peer review through the same pull-request workflow used for code—useful well beyond engineering teams.
* **Portability.** The same source files can render in an IDE, compile to a static site or PDF, or feed a search index. Content is not locked to any one tool's storage format.
* **Longevity.** Plain text survives tool migrations. A directory of Markdown files written today will still open cleanly in whatever editor exists a decade from now.

---

## The Remaining Gap: Readers Live in Confluence

For many organizations, Confluence is where documents are read, searched, commented on, and discussed. That is unlikely to change, and it should not have to—it serves readers well.

The gap is between the authoring layer (Markdown, local files, AI-assisted) and the consumption layer (Confluence pages). Bridging it by hand—copy, paste, fix formatting, re-create links, re-upload images—is tedious enough that documentation quietly stops being updated. The productivity gained in authoring is lost at the publishing step.

---

## Closing the Gap with `confluence-sync`

`confluence-sync` is a command-line tool that publishes a directory of Markdown files to Confluence Cloud and keeps it in sync as the files evolve. It uses Confluence's REST API v2 and aims to be predictable and non-destructive:

* **Renames don't lose history.** A local state file maps each file path to its Confluence page ID. Renaming or moving a file results in an in-place page update, so page history, incoming links, and reader comments survive.
* **Folders map to native Confluence folders.** Directory structure carries over without title collisions between folders and pages.
* **Relative links and anchors resolve automatically.** Cross-page links written naturally in Markdown work on Confluence, including on a first-time sync.
* **Mermaid diagrams render as images.** Diagram blocks are compiled to PNGs and attached to the page.
* **Repository boundaries are enforced.** Only assets inside the project root are uploaded.

The author's workflow stays where it is productive—local files, AI assistance, version control—and Confluence stays what it is good at: a place for readers.

---

## Getting Started

### Step 1: Install
```bash
pipx install confluence-sync
```

### Step 2: Initialize
From the root of your documentation directory:
```bash
confluence-sync init
```
This creates a `.confluence-sync/` folder with a configuration file and a `.gitignore` for local sync state.

### Step 3: Configure a destination
Edit `.confluence-sync/confluence-sync.yml`:

```yaml
destinations:
  - id: ops-briefs
    name: Operations and Strategy Briefs
    confluence:
      url: https://your-company.atlassian.net
      space_key: OPS
      root_page_title: Strategy and Operations
      root_page_id: null      # created on first sync, or pin an existing page ID
    source:
      folders:
        - path: strategy-docs # local folder of Markdown files
          create_root_parent: true
    credentials:
      username: editor@your-company.com
      token_env_var: CONFLUENCE_TOKEN
    options:
      add_git_metadata: true  # footer noting when the document was last updated
      dry_run: false
```

### Step 4: Check the setup
With your Atlassian API token in place (in `~/.local/confluence-sync/.env`):
```bash
confluence-sync doctor -d ops-briefs
```

### Step 5: Preview, then sync
```bash
confluence-sync sync -d ops-briefs --dry-run
confluence-sync sync -d ops-briefs
```

The dry run shows what would change; the live run publishes it. Subsequent syncs only touch pages whose content actually changed, and each run produces a report of what was created, updated, or skipped.

---

## Closing Thought

The case for Markdown-first authoring is ultimately a case about where an author's time goes. Drafting with an AI assistant in plain text is markedly faster than composing in a browser editor, and the surrounding benefits—version control, portability, longevity—come along without extra effort. What remained was the unglamorous work of getting that content in front of readers in Confluence. That part is now a command.

---

## Links & Resources

* **Git Repository**: [zeta-oss/confluence-sync on GitHub](https://github.com/zeta-oss/confluence-sync)
* **Published Documentation**: [Confluence Sync Space in CTO Docs](https://zeta-tm.atlassian.net/wiki/pages/viewpage.action?pageId=5107351560) (synchronized natively using the tool)

