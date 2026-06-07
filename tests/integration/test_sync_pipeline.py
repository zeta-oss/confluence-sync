"""Integration tests for sync_destination orchestration with mocked Confluence."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest.mock import patch

import pytest

from confluence_sync.sync import sync_destination
from confluence_sync.sync_state import load_sync_state


def _mini_git_project(tmp_path: Path) -> Path:
    root = tmp_path / "mini-project"
    docs = root / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n\nHome page.\n", encoding="utf-8")
    (docs / "guide.md").write_text("# Guide\n\nGuide content.\n", encoding="utf-8")
    (nested / "child.md").write_text("# Child\n\nNested page.\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _destination_config() -> Dict[str, Any]:
    return {
        "name": "Pipeline Test",
        "confluence": {
            "url": "https://example.atlassian.net",
            "space_key": "TEST",
            "root_page_title": "Pipeline Root",
            "root_page_id": None,
        },
        "source": {
            "folders": [{"path": "docs", "create_root_parent": True}],
        },
        "credentials": {
            "username": "user@example.com",
            "token_env_var": "CONFLUENCE_TOKEN",
        },
        "options": {
            "add_git_metadata": False,
            "dry_run": False,
            "parallel_threads": 1,
        },
    }


class FakeConfluenceSync:
    """Minimal stand-in for ConfluenceSync API used by sync_destination."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.base_url = "https://example.atlassian.net/wiki"
        self.space_id = "space-1"
        self._page_counter = 1000
        self._folder_counter = 2000

    def get_space_homepage_id(self) -> Optional[str]:
        return "home-1"

    def create_folder(
        self,
        title: str,
        space_id: str,
        parent_id: Optional[str] = None,
        root_page_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        self._folder_counter += 1
        return str(self._folder_counter), "created"

    def find_or_create_page(
        self,
        file_path: str,
        title: str,
        title_original: str,
        storage_format: str,
        content_hash: str,
        parent_id: Optional[str],
        sync_state_entry: Optional[Dict[str, Any]],
        previous_content_hash: Optional[str] = None,
        previous_parent_id: Optional[str] = None,
        previous_title: Optional[str] = None,
        previous_version: Optional[int] = None,
        root_page_id: Optional[str] = None,
    ) -> Tuple[str, str, Optional[int], str]:
        if sync_state_entry and sync_state_entry.get("page_id"):
            page_id = str(sync_state_entry["page_id"])
            if sync_state_entry.get("content_hash") == content_hash:
                return page_id, "skipped", sync_state_entry.get("version", 1), title
            return page_id, "updated", (sync_state_entry.get("version") or 1) + 1, title

        self._page_counter += 1
        return str(self._page_counter), "created", 1, title


@pytest.fixture
def pipeline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_TOKEN", "test-token")


def test_sync_pipeline_clean_incremental_update(tmp_path: Path, pipeline_env: None) -> None:
    project_root = _mini_git_project(tmp_path)
    state_dir = tmp_path / "state"
    dest = _destination_config()

    with patch("confluence_sync.sync.ConfluenceSync", FakeConfluenceSync):
        results1 = sync_destination(
            destination_id="pipe-test",
            destination_config=dest,
            project_root=project_root,
            state_dir=state_dir,
        )

    errors1 = [r for r in results1 if r.status == "error"]
    assert not errors1, [r.error_message for r in errors1]

    state = load_sync_state("pipe-test", state_dir)
    history = state.get("sync_history", {})
    assert history
    for entry in history.values():
        assert entry.get("content_hash")

    with patch("confluence_sync.sync.ConfluenceSync", FakeConfluenceSync):
        results2 = sync_destination(
            destination_id="pipe-test",
            destination_config=dest,
            project_root=project_root,
            state_dir=state_dir,
        )

    assert all(r.status == "skipped" for r in results2)
    assert not any(r.status == "updated" for r in results2)

    guide = project_root / "docs" / "guide.md"
    guide.write_text(guide.read_text(encoding="utf-8") + "\n\nUpdated paragraph.\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/guide.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "update guide"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    with patch("confluence_sync.sync.ConfluenceSync", FakeConfluenceSync):
        results3 = sync_destination(
            destination_id="pipe-test",
            destination_config=dest,
            project_root=project_root,
            state_dir=state_dir,
        )

    updated = [r for r in results3 if r.status == "updated"]
    assert len(updated) == 1
    assert updated[0].file_path.endswith("guide.md")
