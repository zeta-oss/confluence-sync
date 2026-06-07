# 0020. User-local `.env` Loading

**Status:** Accepted (supersedes ADR 0014)
**Date:** 2026-06-01

## Context

ADR 0014 solved credential loading with a shell wrapper script that sourced a `.env` file before calling the Python sync script. This was tied to the embedded-scripts model.

With the standalone CLI, we need an equivalent mechanism that:
- Works across shells without a wrapper
- Keeps credentials out of repos
- Is transparent (the CLI loads it automatically)

## Decision

At startup, the CLI calls `paths.load_dotenv()`, which loads `~/.local/confluence-sync/.env` using `python-dotenv` if the file exists.

This file is:
- Never committed (lives in the user's home directory)
- Created manually: `echo 'CONFLUENCE_TOKEN=...' >> ~/.local/confluence-sync/.env`
- Loaded before any config or credential resolution

`paths.user_local_dir()` returns `~/.local/confluence-sync/` — the directory for all user-global files.

## Consequences

- No shell wrappers needed
- Credentials stay in user home, not in the repo
- `CONFLUENCE_TOKEN` can also be set in the environment directly (takes precedence over `.env`)
- `python-dotenv` added as a runtime dependency
