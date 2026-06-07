"""
Path resolution for confluence-sync.

All config, state, and project-root discovery lives here.
See ADR 0016 (project-local .confluence-sync/), ADR 0017 (user-global ~/.local/),
ADR 0018 (git repo as project root), ADR 0020 (config discovery), ADR 0025 (env loading).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProjectRootError(Exception):
    """Raised when a valid Git project root cannot be found."""


# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------


def resolve_project_root(override: Optional[str | Path] = None) -> Path:
    """
    Resolve the project root directory.

    Priority:
      1. ``override`` (must contain a ``.git`` directory)
      2. Walk up from ``Path.cwd()`` until ``.git`` is found

    Raises:
        ProjectRootError: if no valid root found.
    """
    if override is not None:
        root = Path(override).resolve()
        if not (root / ".git").exists():
            raise ProjectRootError(
                f"--project-root '{root}' does not contain a .git directory. "
                "Provide a valid Git repository root."
            )
        return root

    current = Path.cwd().resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise ProjectRootError(
        "Not inside a Git repository. "
        "Use --project-root to specify your repo root or cd into a repo."
    )


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------

_CONFIG_FILENAME = "confluence-sync.yml"
_LEGACY_CONFIG_FILENAME = "confluence-destinations.yaml"


def resolve_config_path(
    explicit: Optional[str | Path] = None,
    project_root: Optional[Path] = None,
) -> Path:
    """
    Resolve the config file path.

    Priority:
      1. ``explicit`` (``--config PATH``)
      2. ``{project_root}/.confluence-sync/confluence-sync.yml``  (P1)
      3. ``~/.local/confluence-sync/confluence-sync.yml``         (P2)

    A DeprecationWarning is emitted if the legacy ``confluence-destinations.yaml``
    filename is found and used.

    Raises:
        FileNotFoundError: if no config found at any location.
    """
    if explicit is not None:
        p = Path(explicit).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p

    candidates: list[Path] = []

    if project_root is not None:
        candidates.append(project_root / ".confluence-sync" / _CONFIG_FILENAME)
        candidates.append(project_root / ".confluence-sync" / _LEGACY_CONFIG_FILENAME)

    candidates.append(user_local_dir() / _CONFIG_FILENAME)
    candidates.append(user_local_dir() / _LEGACY_CONFIG_FILENAME)

    for path in candidates:
        if path.exists():
            if path.name == _LEGACY_CONFIG_FILENAME:
                import warnings

                warnings.warn(
                    f"Config file '{path.name}' is deprecated. "
                    f"Rename it to '{_CONFIG_FILENAME}'.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            return path

    searched = "\n  ".join(
        str(c) for c in candidates if c.name != _LEGACY_CONFIG_FILENAME
    )
    raise FileNotFoundError(
        f"No confluence-sync configuration found. Searched:\n  {searched}\n"
        "Run 'confluence-sync init' to create a project config."
    )


# ---------------------------------------------------------------------------
# State directory resolution
# ---------------------------------------------------------------------------


def resolve_state_dir(
    project_root: Optional[Path] = None,
    override: Optional[str | Path] = None,
) -> Path:
    """
    Resolve the state directory.

    Priority:
      1. ``override`` (``--state-dir PATH``)
      2. ``{project_root}/.confluence-sync/destinations/``

    Raises:
        ValueError: if neither argument is provided.
    """
    if override is not None:
        return Path(override).resolve()
    if project_root is not None:
        return project_root / ".confluence-sync" / "destinations"
    raise ValueError("Either project_root or override must be provided to resolve_state_dir().")


def destination_state_dir(state_dir: Path, destination_id: str) -> Path:
    """Return (and create) the per-destination subdirectory under state_dir."""
    d = state_dir / destination_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# User-global directory
# ---------------------------------------------------------------------------


def user_local_dir() -> Path:
    """Return ``~/.local/confluence-sync/``."""
    return Path.home() / ".local" / "confluence-sync"


def mermaid_cache_dir() -> Path:
    """Return (and create) the user-global Mermaid PNG cache directory."""
    d = user_local_dir() / "mermaid-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    """Return the optional user-global logs directory."""
    return user_local_dir() / "logs"


# ---------------------------------------------------------------------------
# Environment / .env loading
# ---------------------------------------------------------------------------


def load_dotenv(project_root: Optional[Path] = None) -> None:
    """
    Load .env files in priority order (later sources do NOT override earlier).

    Order (ADR 0025):
      1. Already-exported shell env vars (always win — never overwritten)
      2. ``~/.local/confluence-sync/.env``
      3. ``{project_root}/.env``  (optional convenience)
    """
    _load_dotenv_file(user_local_dir() / ".env")
    if project_root is not None:
        _load_dotenv_file(project_root / ".env")


def _load_dotenv_file(path: Path) -> None:
    """Parse a simple ``KEY=VALUE`` .env file. Skips keys already in os.environ."""
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


# ---------------------------------------------------------------------------
# SyncContext — carries resolved paths through all sync phases
# ---------------------------------------------------------------------------


class SyncContext:
    """Carries resolved path state through sync phases."""

    __slots__ = ("project_root", "config_path", "state_dir", "user_dir")

    def __init__(
        self,
        project_root: Path,
        config_path: Path,
        state_dir: Path,
        user_dir: Optional[Path] = None,
    ) -> None:
        self.project_root = project_root
        self.config_path = config_path
        self.state_dir = state_dir
        self.user_dir = user_dir or user_local_dir()

    @classmethod
    def from_args(
        cls,
        project_root_arg: Optional[str] = None,
        config_arg: Optional[str] = None,
        state_dir_arg: Optional[str] = None,
    ) -> "SyncContext":
        """Build a SyncContext from CLI argument strings."""
        root = resolve_project_root(project_root_arg)
        load_dotenv(root)
        cfg = resolve_config_path(config_arg, root)
        state = resolve_state_dir(root, state_dir_arg)
        return cls(root, cfg, state)
