"""Unit tests for orphan_handler.py — ported from test_orphan_handler.py."""

from __future__ import annotations

from unittest.mock import Mock

from confluence_sync.orphan_handler import OrphanHandler


def _make_sync_state():
    return {
        "destination_id": "dest",
        "sync_history": {
            "docs/index.md": {"page_id": "111", "page_title": "Index"},
            "docs/old.md": {"page_id": "222", "page_title": "Old Page"},
        },
        "folders": {
            "docs/old-folder": {
                "folder_id": "f333",
                "folder_title": "Old Folder",
                "parent_id": "root",
            }
        },
    }


class TestFindOrphans:
    def setup_method(self):
        self.mock_confluence = Mock()
        self.handler = OrphanHandler(self.mock_confluence)

    def test_finds_deleted_page(self):
        state = _make_sync_state()
        discovered = {"docs/index.md"}  # old.md is gone
        orphan_pages, orphan_folders = self.handler.find_orphans(
            state, discovered, renamed_files=set()
        )
        assert len(orphan_pages) == 1
        assert orphan_pages[0]["path"] == "docs/old.md"

    def test_renamed_file_not_in_orphans(self):
        state = _make_sync_state()
        discovered = {"docs/index.md", "docs/new-name.md"}
        orphan_pages, _ = self.handler.find_orphans(
            state, discovered, renamed_files={"docs/old.md"}
        )
        assert not any(o["path"] == "docs/old.md" for o in orphan_pages)

    def test_finds_deleted_folder(self):
        state = _make_sync_state()
        discovered = {"docs/index.md", "docs/old.md"}
        _, orphan_folders = self.handler.find_orphans(
            state, discovered, renamed_files=set(), discovered_folders=set()
        )
        assert len(orphan_folders) == 1
        assert orphan_folders[0]["folder_id"] == "f333"

    def test_no_orphans_when_all_discovered(self):
        state = _make_sync_state()
        discovered = {"docs/index.md", "docs/old.md"}
        discovered_folders = {"docs/old-folder"}
        orphan_pages, orphan_folders = self.handler.find_orphans(
            state, discovered, renamed_files=set(), discovered_folders=discovered_folders
        )
        assert orphan_pages == []
        assert orphan_folders == []


class TestDeleteOrphans:
    def setup_method(self):
        self.mock_confluence = Mock()
        self.mock_confluence.delete_page_v2.return_value = True
        self.mock_confluence.delete_folder.return_value = True
        self.handler = OrphanHandler(self.mock_confluence)

    def test_deletes_orphan_pages(self):
        orphan_pages = [{"path": "docs/old.md", "page_id": "222", "page_title": "Old Page"}]
        deleted = self.handler.delete_orphans(orphan_pages, [])
        assert "docs/old.md" in deleted
        self.mock_confluence.delete_page_v2.assert_called_once_with("222")

    def test_skips_orphan_without_page_id(self):
        orphan_pages = [{"path": "docs/missing.md", "page_id": None, "page_title": "Missing"}]
        deleted = self.handler.delete_orphans(orphan_pages, [])
        assert deleted == []
