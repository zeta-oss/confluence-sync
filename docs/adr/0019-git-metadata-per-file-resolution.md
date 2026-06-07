# 0019. Git Metadata Per-file Path Resolution

**Status:** Accepted
**Date:** 2026-06-01

## Context

The CLI generates a Git metadata footer for each synced page: commit hash and a GitHub blob URL (`github.com/{org}/{repo}/blob/{sha}/{path}`).

The original `git_utils.py` sometimes produced URLs with `../` segments when the source folder was outside the Git root, or when `file_path` and `repo_root` were passed as relative paths.

With cross-repo source paths removed (ADR 0015), all source files are inside a single Git repo. However, `get_file_github_url()` must still produce clean paths.

## Decision

`git_utils.get_file_github_url(file_path, repo_root)` now:

1. Resolves both `file_path` and `repo_root` to absolute paths via `Path.resolve()`
2. Computes `relative = file_path.relative_to(repo_root)` — raises `ValueError` if outside
3. Formats the URL as `{github_url}/blob/{sha}/{relative}` — no `../` segments possible

The `git_root` parameter (where `git log` is run from) is separate from the `repo_root` used for the URL path. This allows a subdirectory to be the URL root while using a parent Git repo for metadata.

## Consequences

- No `../` segments in GitHub URLs
- `ValueError` raised early if a file is genuinely outside the repo root
- Behaviour is deterministic regardless of `cwd` at call time
