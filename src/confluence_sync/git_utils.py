"""
Git utilities for commit metadata and GitHub blob URLs.

Key fixes (ADR 0019):
- Always resolve() file_path before relative_to()
- Per-file git_root: folder.git_root → auto-detect from file → project_root
- Run git commands in the correct repo root (not the install host)
- Normalise SSH remote git@github.com:org/repo.git → https://github.com/org/repo
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------


def get_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """Walk up from start_path (or cwd) to find a .git directory."""
    current = (Path(start_path) if start_path else Path.cwd()).resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def resolve_git_root_for_file(
    file_path: Path,
    folder_git_root: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve the git root to use for a specific file.

    Priority (ADR 0019):
      1. folder.git_root config override (explicit)
      2. Auto-detect from file_path (walk up to .git)
      3. project_root fallback
    """
    if folder_git_root is not None:
        return Path(folder_git_root).resolve()
    detected = get_repo_root(file_path.parent if file_path.is_absolute() else None)
    if detected:
        return detected
    return project_root


# ---------------------------------------------------------------------------
# Commit metadata
# ---------------------------------------------------------------------------


def get_current_commit_hash(repo_root: Optional[Path] = None) -> Optional[str]:
    """Short HEAD commit hash, or None on error."""
    cwd = Path(repo_root).resolve() if repo_root else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_full_commit_hash(repo_root: Optional[Path] = None) -> Optional[str]:
    """Full HEAD commit hash, or None on error."""
    cwd = Path(repo_root).resolve() if repo_root else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_file_commit_hash(
    file_path: Path,
    repo_root: Optional[Path] = None,
) -> Optional[str]:
    """Short hash of the last commit that touched file_path."""
    file_path = file_path.resolve()
    root = repo_root or get_repo_root(file_path.parent)
    if root is None:
        return None
    try:
        rel = file_path.relative_to(root.resolve())
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(rel)],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        h = result.stdout.strip()
        return h[:7] if h else None
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


def get_file_commit_date(
    file_path: Path,
    repo_root: Optional[Path] = None,
) -> Optional[str]:
    """ISO date of the last commit that touched file_path."""
    file_path = file_path.resolve()
    root = repo_root or get_repo_root(file_path.parent)
    if root is None:
        return None
    try:
        rel = file_path.relative_to(root.resolve())
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(rel)],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------


def _normalise_remote_url(raw: str) -> Optional[str]:
    """
    Convert an SSH or HTTPS git remote URL to a plain HTTPS GitHub URL.

    Returns None if the remote is not GitHub.
    """
    url = raw.strip()
    # Strip .git suffix
    if url.endswith(".git"):
        url = url[:-4]
    # SSH: git@github.com:org/repo
    if url.startswith("git@github.com:"):
        url = url.replace("git@github.com:", "https://github.com/", 1)
    elif url.startswith("git@"):
        url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    if "github.com" not in url:
        return None
    return url.rstrip("/")


def get_github_repo_url(
    repo_root: Optional[Path] = None,
    override: Optional[str] = None,
) -> Optional[str]:
    """Return the GitHub base URL (no trailing slash). None if not on GitHub."""
    if override:
        return override.rstrip("/")
    cwd = Path(repo_root).resolve() if repo_root else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return _normalise_remote_url(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_file_github_url(
    file_path: Path,
    repo_root: Optional[Path] = None,
    github_repo_override: Optional[str] = None,
    commit_hash: Optional[str] = None,
    folder_git_root: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Optional[str]:
    """
    Build the GitHub blob URL for a file at a specific commit.

    Uses resolve_git_root_for_file to pick the correct repo for git operations.
    Always resolves file_path to avoid ../sibling-repo path segments (ADR 0019).
    """
    file_path = file_path.resolve()

    effective_root = resolve_git_root_for_file(file_path, folder_git_root, project_root)
    if effective_root is None:
        return None

    repo_url = get_github_repo_url(effective_root, github_repo_override)
    if not repo_url:
        return None

    if commit_hash is None:
        commit_hash = get_full_commit_hash(effective_root)
    if not commit_hash:
        return None

    try:
        rel = file_path.relative_to(effective_root.resolve())
    except ValueError:
        return None

    rel_str = str(rel).replace("\\", "/")
    return f"{repo_url}/blob/{commit_hash}/{rel_str}"
