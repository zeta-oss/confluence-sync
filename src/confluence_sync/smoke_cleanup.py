"""
Smoke cleanup — delete Confluence smoke subtree and wipe local state.

Used by `confluence-sync smoke reset` and the release teardown trap.
See ADR 0024 (test resource cleanup), ADR 0028 (smoke subcommand).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class SmokeCleanup:
    """Delete descendants of a smoke root page and wipe local state."""

    def __init__(
        self,
        base_url: str,
        username: str,
        token: str,
        space_key: str,
        root_page_id: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (username, token)
        self.space_key = space_key
        self.root_page_id = root_page_id

    @classmethod
    def from_destination(cls, dest: Dict[str, Any]) -> "SmokeCleanup":
        import os

        cfg = dest["confluence"]
        creds = dest["credentials"]
        token = os.getenv(creds["token_env_var"], "")
        return cls(
            base_url=cfg["url"],
            username=creds["username"],
            token=token,
            space_key=cfg["space_key"],
            root_page_id=cfg.get("root_page_id"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, state_dir: Path, destination_id: str) -> None:
        """
        Delete all Confluence child pages under smoke root and wipe local state.

        Always runs — called from `finally` blocks and `trap EXIT`.
        """
        if self.root_page_id and self.auth[1]:
            self.delete_descendants(self.root_page_id)
        else:
            print("  ⚠ No root_page_id or token — skipping Confluence cleanup")

        self.wipe_local_state(state_dir, destination_id)

    def delete_descendants(self, root_page_id: str) -> None:
        """Walk children via v2 API and delete them (folders then pages)."""
        try:
            self._delete_descendants_recursive(root_page_id)
            print(f"  ✓ Deleted descendants under {root_page_id}")
        except Exception as exc:
            print(f"  ⚠ Could not delete descendants of {root_page_id}: {exc}")

    def delete_subtree_including_root(self, root_page_id: str) -> None:
        """Delete all descendants then the root page/folder itself."""
        try:
            self._delete_descendants_recursive(root_page_id)
            self._delete_item(root_page_id, item_type="page")
            print(f"  ✓ Deleted subtree including root {root_page_id}")
        except Exception as exc:
            print(f"  ⚠ Could not delete subtree for {root_page_id}: {exc}")

    def find_page_by_title(self, title: str) -> Optional[str]:
        """Return page id for exact title in space, or None."""
        escaped = title.replace('"', '\\"')
        cql = f'space = {self.space_key} AND type = page AND title = "{escaped}"'
        url = f"{self.base_url}/wiki/rest/api/content/search"
        import requests

        resp = requests.get(
            url,
            params={"cql": cql, "limit": 5},
            auth=self.auth,
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        return str(results[0].get("id"))

    def _delete_descendants_recursive(self, root_page_id: str) -> None:
        children = self._get_children(root_page_id)
        folders = [c for c in children if c.get("type") == "folder"]
        pages = [c for c in children if c.get("type") != "folder"]

        for folder in folders:
            fid = folder.get("id")
            self._delete_descendants_recursive(fid)
            self._delete_item(fid, item_type="folder")

        for page in pages:
            pid = page.get("id")
            self._delete_descendants_recursive(pid)
            self._delete_item(pid, item_type="page")

    def wipe_local_state(self, state_dir: Path, destination_id: str) -> None:
        """Remove the per-destination state directory."""
        dest_dir = state_dir / destination_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
            print(f"  ✓ Wiped local state: {dest_dir}")

    def assert_cleanup_complete(self, root_page_id: str) -> bool:
        """Return True if smoke root has zero children (post-teardown check)."""
        children = self._get_children(root_page_id)
        if children:
            print(f"  ✗ {len(children)} child(ren) remain under smoke root")
            return False
        print("  ✓ Smoke root is clean")
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        import requests

        url = f"{self.base_url}/wiki/api/v2/{path.lstrip('/')}"
        resp = requests.get(url, auth=self.auth, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_children(self, page_id: str) -> List[Dict[str, Any]]:
        try:
            data = self._get(f"pages/{page_id}/children")
            return data.get("results", [])
        except Exception:
            return []

    def _delete_item(self, item_id: str, item_type: str = "page") -> None:
        import requests

        path = "pages" if item_type != "folder" else "folders"
        url = f"{self.base_url}/wiki/api/v2/{path}/{item_id}"
        resp = requests.delete(url, auth=self.auth, timeout=30)
        if resp.status_code not in (200, 204):
            print(f"  ⚠ Could not delete {item_type} {item_id}: {resp.status_code}")
