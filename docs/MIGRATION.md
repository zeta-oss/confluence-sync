# Migration Guide — from `_confluence_sync` embedded scripts

This guide covers migrating from the embedded `_confluence_sync/scripts/` pattern
to the standalone `confluence-sync` CLI.

---

## What changed

| Before | After |
|--------|-------|
| `_confluence_sync/scripts/sync-to-confluence.py` run via shell script | `confluence-sync sync -d <id>` |
| `_confluence_sync/data/confluence-destinations.yaml` | `.confluence-sync/confluence-sync.yml` (per repo root) |
| `_confluence_sync/data/{id}/` — state data mixed in strategy repo | `.confluence-sync/destinations/{id}/` — local to each consuming repo |
| `../writing-work/...` cross-repo source paths | Separate `.confluence-sync/` in `writing-work` repo |
| Manual `source .venv/bin/activate && python ...` | `confluence-sync sync -d <id>` (installed CLI) |

---

## Step-by-step migration

### 1. Install the CLI

```bash
brew tap zeta-oss/confluence-sync https://github.com/zeta-oss/confluence-sync.git
brew install confluence-sync
# or: pip install confluence-sync
```

### 2. Initialise each repo

For each Git repo that previously had destinations pointing into it:

```bash
cd ~/Git/my-repo
confluence-sync init
```

Edit `.confluence-sync/confluence-sync.yml` and add your destinations.
Use only **relative paths** inside the repo — no `../other-repo` paths.

### 3. Move state data

Copy existing state from `_confluence_sync/data/{id}/` into
`.confluence-sync/destinations/{id}/`:

```bash
# In the repo root (e.g. zeta-ai-product-strategy)
mkdir -p .confluence-sync/destinations
cp -r _confluence_sync/data/my-destination .confluence-sync/destinations/my-destination
```

The state format (JSONL) is compatible — no conversion needed.

### 4. Move credentials

If `CONFLUENCE_TOKEN` was exported in a repo-local script, move it to
the user-local env file (never committed):

```bash
mkdir -p ~/.local/confluence-sync
echo "CONFLUENCE_TOKEN=your-token" >> ~/.local/confluence-sync/.env
```

### 5. Run doctor

```bash
confluence-sync doctor -d my-destination
```

Fix any reported issues before running a real sync.

### 6. Test with dry-run

```bash
confluence-sync sync -d my-destination --dry-run
```

Verifies content preparation without writing to Confluence.

### 7. First live sync

```bash
confluence-sync sync -d my-destination
```

---

## Cross-repo source paths (`../writing-work`)

The old config had destinations with `path: ../writing-work/...`.
The new CLI enforces source folders to be **inside** the project root.

**Migration**: move those destinations to the `writing-work` repo's own
`.confluence-sync/confluence-sync.yml`, with `path: term-deposits` instead
of `path: ../writing-work/term-deposits`.

---

## Config field changes

The YAML schema is identical to `confluence-destinations.yaml` except:
- The file lives at `.confluence-sync/confluence-sync.yml` (project-local)
- No `../` source paths
- `options.parallel_threads` — unchanged, still supported

---

## `.gitignore` additions

After migration, add to your repo's `.gitignore` (or the generated one is
already in `.confluence-sync/.gitignore`):

```gitignore
.confluence-sync/destinations/
```

---

## Deprecating the embedded scripts

Once all destinations are migrated and verified:

1. Update `_confluence_sync/README.md` with a deprecation notice (done).
2. Stop running `_confluence_sync/scripts/sync-*.sh` shell scripts.
3. Optionally archive `_confluence_sync/` (do not delete until state is confirmed migrated).

---

## Rollback

If you need to revert to the old scripts temporarily:

1. The old `_confluence_sync/` scripts still work — nothing was deleted.
2. The state in `.confluence-sync/destinations/{id}/` is a copy of the old
   `_confluence_sync/data/{id}/` — both are JSONL-compatible.
