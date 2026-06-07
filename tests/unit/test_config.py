"""Unit tests for config.py."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from confluence_sync.config import (
    ConfigError,
    get_destination,
    load_destination_config,
    resolve_credentials,
    validate_destination_config,
)


def _write_config(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _minimal_dest(project_root: Path) -> dict:
    (project_root / "docs").mkdir(exist_ok=True)
    return {
        "id": "test",
        "name": "Test",
        "confluence": {
            "url": "https://x.atlassian.net",
            "space_key": "TST",
            "root_page_title": "Root",
        },
        "source": {"folders": [{"path": "docs", "create_root_parent": True}]},
        "credentials": {"username": "u@e.com", "token_env_var": "CONF_TOKEN"},
    }


# ---------------------------------------------------------------------------
# load_destination_config
# ---------------------------------------------------------------------------


def test_valid_minimal(tmp_path):
    (tmp_path / "docs").mkdir()
    cfg = _write_config(
        tmp_path / "c.yml",
        {"destinations": [_minimal_dest(tmp_path)]},
    )
    result = load_destination_config(cfg, tmp_path)
    assert len(result["destinations"]) == 1


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_destination_config(tmp_path / "missing.yml")


def test_missing_destinations_key(tmp_path):
    cfg = _write_config(tmp_path / "c.yml", {"other": 1})
    with pytest.raises(ConfigError, match="'destinations'"):
        load_destination_config(cfg)


def test_empty_destinations(tmp_path):
    cfg = _write_config(tmp_path / "c.yml", {"destinations": []})
    with pytest.raises(ConfigError, match="At least one"):
        load_destination_config(cfg)


# ---------------------------------------------------------------------------
# validate_destination_config
# ---------------------------------------------------------------------------


def test_folder_outside_project_root_rejected(tmp_path):
    (tmp_path / "docs").mkdir()
    dest = {
        "id": "x",
        "name": "X",
        "confluence": {
            "url": "https://x.atlassian.net",
            "space_key": "X",
            "root_page_title": "Root",
        },
        "source": {"folders": [{"path": "../sibling-repo/docs"}]},
        "credentials": {"username": "u", "token_env_var": "T"},
    }
    with pytest.raises(ConfigError, match="project root"):
        validate_destination_config(dest, tmp_path)


def test_absolute_path_rejected(tmp_path):
    dest = {
        "id": "x",
        "name": "X",
        "confluence": {
            "url": "https://x.atlassian.net",
            "space_key": "X",
            "root_page_title": "Root",
        },
        "source": {"folders": [{"path": str(tmp_path / "docs")}]},
        "credentials": {"username": "u", "token_env_var": "T"},
    }
    with pytest.raises(ConfigError, match="relative"):
        validate_destination_config(dest, tmp_path)


def test_parallel_threads_bounds(tmp_path):
    (tmp_path / "docs").mkdir()
    dest = _minimal_dest(tmp_path)
    dest["options"] = {"parallel_threads": 100}
    with pytest.raises(ConfigError, match="parallel_threads"):
        validate_destination_config(dest, tmp_path)


def test_parallel_threads_valid(tmp_path):
    (tmp_path / "docs").mkdir()
    dest = _minimal_dest(tmp_path)
    dest["options"] = {"parallel_threads": 10}
    validate_destination_config(dest, tmp_path)  # Should not raise


# ---------------------------------------------------------------------------
# get_destination
# ---------------------------------------------------------------------------


def test_get_destination_found(tmp_path):
    (tmp_path / "docs").mkdir()
    config = {"destinations": [_minimal_dest(tmp_path)]}
    result = get_destination(config, "test")
    assert result["id"] == "test"


def test_get_destination_not_found(tmp_path):
    (tmp_path / "docs").mkdir()
    config = {"destinations": [_minimal_dest(tmp_path)]}
    with pytest.raises(ConfigError, match="not found"):
        get_destination(config, "missing")


# ---------------------------------------------------------------------------
# resolve_credentials
# ---------------------------------------------------------------------------


def test_resolve_credentials_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("CONF_TOKEN", raising=False)
    dest = _minimal_dest(tmp_path)
    with pytest.raises(ConfigError, match="CONF_TOKEN"):
        resolve_credentials(dest)


def test_resolve_credentials_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("CONF_TOKEN", "mytoken")
    dest = _minimal_dest(tmp_path)
    result = resolve_credentials(dest)
    assert result["token"] == "mytoken"
    assert result["username"] == "u@e.com"


# ---------------------------------------------------------------------------
# list_destination_ids
# ---------------------------------------------------------------------------


def test_list_destination_ids(tmp_path):
    (tmp_path / "docs").mkdir()
    config = {"destinations": [{"id": "first"}, {"id": "second"}]}
    ids = [d["id"] for d in config["destinations"]]
    assert "first" in ids
    assert "second" in ids
