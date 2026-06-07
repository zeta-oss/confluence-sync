"""
Shared pytest fixtures for confluence-sync tests.

Cleanup policy (ADR 0024):
- All git repos and state dirs go in pytest tmp_path / tmp_path_factory.
- HOME is monkeypatched so tests never touch ~/.local/confluence-sync/.
- No test writes outside tmp_path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Isolated HOME
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect HOME to tmp_path so no test touches ~/.local/confluence-sync/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Project root with .git
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_project_root(tmp_path: Path) -> Path:
    """A tmp_path with a .git dir and a minimal doc tree."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()

    docs = root / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Index\n\nWelcome.\n", encoding="utf-8")
    (docs / "guide.md").write_text("# Guide\n\nContent here.\n", encoding="utf-8")

    sub = docs / "sub"
    sub.mkdir()
    (sub / "detail.md").write_text("# Detail\n\nDetail page.\n", encoding="utf-8")

    return root


@pytest.fixture()
def git_project_root(tmp_path: Path) -> Path:
    """A tmp_path with a real git repo (git init + initial commit)."""
    root = tmp_path / "git-project"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True
    )

    docs = root / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Index\n", encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True
    )
    return root


# ---------------------------------------------------------------------------
# Minimal valid config
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config(fake_project_root: Path) -> Path:
    """Write a minimal confluence-sync.yml and return its path."""
    cs_dir = fake_project_root / ".confluence-sync"
    cs_dir.mkdir()
    config_path = cs_dir / "confluence-sync.yml"
    config = {
        "destinations": [
            {
                "id": "test-dest",
                "name": "Test Destination",
                "confluence": {
                    "url": "https://test.atlassian.net",
                    "space_key": "TEST",
                    "root_page_title": "Test Root",
                },
                "source": {
                    "folders": [
                        {"path": "docs", "create_root_parent": True}
                    ]
                },
                "credentials": {
                    "username": "test@test.com",
                    "token_env_var": "CONFLUENCE_TOKEN",
                },
                "options": {
                    "add_git_metadata": False,
                    "dry_run": False,
                },
            }
        ]
    }
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# Fake user local dir
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_user_local(fake_home: Path) -> Path:
    """Return an isolated ~/.local/confluence-sync/ dir."""
    uld = fake_home / ".local" / "confluence-sync"
    uld.mkdir(parents=True)
    return uld
