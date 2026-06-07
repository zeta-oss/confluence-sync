"""Unit tests for paths.py — highest-priority coverage."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from confluence_sync.paths import (
    ProjectRootError,
    SyncContext,
    destination_state_dir,
    load_dotenv,
    resolve_config_path,
    resolve_project_root,
    resolve_state_dir,
    user_local_dir,
)

# ---------------------------------------------------------------------------
# resolve_project_root
# ---------------------------------------------------------------------------


def test_explicit_root_with_git(tmp_path):
    (tmp_path / ".git").mkdir()
    result = resolve_project_root(tmp_path)
    assert result == tmp_path.resolve()


def test_explicit_root_without_git(tmp_path):
    with pytest.raises(ProjectRootError, match=".git"):
        resolve_project_root(tmp_path)


def test_cwd_walkup_finds_root(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "a" / "b" / "c"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    result = resolve_project_root()
    assert result == tmp_path.resolve()


def test_cwd_outside_any_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ProjectRootError, match="Not inside a Git repository"):
        resolve_project_root()


# ---------------------------------------------------------------------------
# resolve_config_path
# ---------------------------------------------------------------------------


def test_config_p1_project_local(tmp_path):
    (tmp_path / ".git").mkdir()
    cs_dir = tmp_path / ".confluence-sync"
    cs_dir.mkdir()
    p1 = cs_dir / "confluence-sync.yml"
    p1.write_text("destinations: []")
    result = resolve_config_path(project_root=tmp_path)
    assert result == p1


def test_config_p2_global_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    global_dir = tmp_path / ".local" / "confluence-sync"
    global_dir.mkdir(parents=True)
    p2 = global_dir / "confluence-sync.yml"
    p2.write_text("destinations: []")
    result = resolve_config_path()
    assert result == p2


def test_explicit_config_override(tmp_path):
    cfg = tmp_path / "custom.yml"
    cfg.write_text("destinations: []")
    result = resolve_config_path(explicit=cfg)
    assert result == cfg


def test_config_not_found_raises(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_config_path(project_root=tmp_path)


def test_legacy_config_name_warns(tmp_path):
    cs_dir = tmp_path / ".confluence-sync"
    cs_dir.mkdir()
    legacy = cs_dir / "confluence-destinations.yaml"
    legacy.write_text("destinations: []")
    with pytest.warns(DeprecationWarning, match="Rename"):
        result = resolve_config_path(project_root=tmp_path)
    assert result == legacy


# ---------------------------------------------------------------------------
# resolve_state_dir
# ---------------------------------------------------------------------------


def test_state_dir_default(tmp_path):
    (tmp_path / ".git").mkdir()
    result = resolve_state_dir(project_root=tmp_path)
    assert result == tmp_path / ".confluence-sync" / "destinations"


def test_state_dir_override(tmp_path):
    override = tmp_path / "custom-state"
    result = resolve_state_dir(override=override)
    assert result == override.resolve()


def test_state_dir_no_args_raises():
    with pytest.raises(ValueError):
        resolve_state_dir()


# ---------------------------------------------------------------------------
# user_local_dir
# ---------------------------------------------------------------------------


def test_user_local_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = user_local_dir()
    assert result == tmp_path / ".local" / "confluence-sync"


# ---------------------------------------------------------------------------
# load_dotenv — env load order
# ---------------------------------------------------------------------------


def test_load_dotenv_does_not_overwrite_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TOKEN", "shell-value")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    uld = tmp_path / ".local" / "confluence-sync"
    uld.mkdir(parents=True)
    (uld / ".env").write_text("MY_TOKEN=env-value\n", encoding="utf-8")

    load_dotenv()
    assert os.environ["MY_TOKEN"] == "shell-value"


def test_load_dotenv_sets_missing_var(monkeypatch, tmp_path):
    monkeypatch.delenv("CSYNC_TEST_VAR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    uld = tmp_path / ".local" / "confluence-sync"
    uld.mkdir(parents=True)
    (uld / ".env").write_text("CSYNC_TEST_VAR=hello\n", encoding="utf-8")

    load_dotenv()
    assert os.environ.get("CSYNC_TEST_VAR") == "hello"
    monkeypatch.delenv("CSYNC_TEST_VAR", raising=False)


# ---------------------------------------------------------------------------
# SyncContext
# ---------------------------------------------------------------------------


def test_sync_context_from_args(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".git").mkdir()
    cs_dir = tmp_path / ".confluence-sync"
    cs_dir.mkdir()
    cfg = cs_dir / "confluence-sync.yml"
    cfg.write_text("destinations: []")
    monkeypatch.chdir(tmp_path)

    ctx = SyncContext.from_args()
    assert ctx.project_root == tmp_path.resolve()
    assert ctx.config_path == cfg


# ---------------------------------------------------------------------------
# destination_state_dir
# ---------------------------------------------------------------------------


def test_destination_state_dir_creates(tmp_path):
    state = tmp_path / "state"
    result = destination_state_dir(state, "my-dest")
    assert result == state / "my-dest"
    assert result.exists()
