"""
Ephemeral Confluence workspace provisioning for live smoke tests.

Each smoke run creates an isolated private space, runs tests inside it, and
deletes the entire space on teardown. A session file survives process crashes
so release traps can still destroy the workspace.

Falls back to a run-scoped root page in an existing space when space creation
is not permitted (unique titles avoid ghost-page conflicts from slow deletes).
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from confluence_sync.paths import user_local_dir


class SmokeProvisionError(Exception):
    """Raised when ephemeral workspace provisioning fails."""


@dataclass(frozen=True)
class EphemeralWorkspace:
    """Runtime workspace binding for a single smoke run."""

    run_id: str
    space_key: str
    mode: str  # "ephemeral_space" | "ephemeral_root"
    root_page_title: str
    root_page_id: Optional[str] = None


_SESSION_FILE = "smoke-session.json"


class SmokeProvisioner:
    """Create and destroy isolated Confluence workspaces for smoke tests."""

    def __init__(self, base_url: str, username: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        if "/wiki" not in self.base_url:
            self.wiki_base = f"{self.base_url}/wiki"
        else:
            self.wiki_base = self.base_url
        self.auth = HTTPBasicAuth(username, token)
        self.timeout = (10, 60)

    @classmethod
    def from_destination(cls, dest: Dict[str, Any]) -> "SmokeProvisioner":
        import os

        cfg = dest["confluence"]
        creds = dest["credentials"]
        token = os.getenv(creds["token_env_var"], "")
        if not token:
            raise SmokeProvisionError(
                f"Token env var '{creds['token_env_var']}' is not set"
            )
        return cls(cfg["url"], creds["username"], token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provision(self, dest: Dict[str, Any]) -> tuple[Dict[str, Any], EphemeralWorkspace]:
        """
        Provision an isolated workspace and return a patched destination config.

        Tries private space creation first; falls back to a unique root page
        under CONFLUENCE_SMOKE_FALLBACK_SPACE or CONFLUENCE_SPACE.
        """
        run_id = uuid.uuid4().hex[:8]
        options = dest.get("options") or {}
        if not options.get("auto_provision_space", True):
            ws = EphemeralWorkspace(
                run_id=run_id,
                space_key=dest["confluence"]["space_key"],
                mode="fixed",
                root_page_title=dest["confluence"]["root_page_title"],
                root_page_id=dest["confluence"].get("root_page_id"),
            )
            return dest, ws

        import os

        force_fallback = os.getenv("SMOKE_FORCE_FALLBACK", "").strip() == "1"
        if not force_fallback:
            try:
                space_key = self._create_private_space(run_id)
                root_title = f"Smoke Root {run_id}"
                ws = EphemeralWorkspace(
                    run_id=run_id,
                    space_key=space_key,
                    mode="ephemeral_space",
                    root_page_title=root_title,
                )
                patched = self._patch_dest(dest, ws)
                self._save_session(ws)
                print(f"  ✓ Created ephemeral space: {space_key} (run {run_id})")
                return patched, ws
            except Exception as exc:
                print(f"  ⚠ Space creation failed ({exc}); using ephemeral root page fallback")
        else:
            print("  ℹ SMOKE_FORCE_FALLBACK=1 — skipping private space creation")

        fallback_key = self._fallback_space_key()
        root_title = f"Smoke Root {run_id}"
        ws = EphemeralWorkspace(
            run_id=run_id,
            space_key=fallback_key,
            mode="ephemeral_root",
            root_page_title=root_title,
        )
        patched = self._patch_dest(dest, ws)
        self._save_session(ws)
        print(f"  ✓ Using fallback space {fallback_key} with root '{root_title}' (run {run_id})")
        return patched, ws

    def destroy_workspace(self, workspace: Optional[EphemeralWorkspace] = None) -> None:
        """Delete ephemeral space or ephemeral root subtree."""
        ws = workspace or self._load_session()
        if ws is None:
            print("  ⚠ No smoke session — nothing to destroy")
            return

        if ws.mode == "ephemeral_space":
            self._delete_space(ws.space_key)
        elif ws.mode == "ephemeral_root":
            self._delete_ephemeral_root(ws)
        else:
            print("  ⚠ Fixed workspace — skipping Confluence destroy")

        self._clear_session()
        print(f"  ✓ Destroyed smoke workspace (run {ws.run_id})")

    def destroy_session_workspace(self) -> None:
        """Destroy workspace recorded in the session file (for traps/reset)."""
        self.destroy_workspace(self._load_session())

    def patch_fixture_mapping(self, fixture_root: Path, run_id: str) -> None:
        """Prefix mapping titles so ghost pages from slow deletes cannot collide."""
        import re

        mapping = fixture_root / ".confluence-mapping.yaml"
        if not mapping.exists():
            return
        text = mapping.read_text(encoding="utf-8")
        prefix = f"Smoke {run_id} - "

        def _repl(match: re.Match[str]) -> str:
            return f'{match.group(1)}{prefix}{match.group(2)}"'

        patched = re.sub(
            r'^(\s*\S+:\s*")Smoke Test - (.+?)"\s*$',
            _repl,
            text,
            flags=re.MULTILINE,
        )
        mapping.write_text(patched, encoding="utf-8")

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _session_path(self) -> Path:
        d = user_local_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / _SESSION_FILE

    def _save_session(self, ws: EphemeralWorkspace) -> None:
        payload = {
            "run_id": ws.run_id,
            "space_key": ws.space_key,
            "mode": ws.mode,
            "root_page_title": ws.root_page_title,
            "root_page_id": ws.root_page_id,
            "base_url": self.base_url,
        }
        self._session_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_session(self) -> Optional[EphemeralWorkspace]:
        path = self._session_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return EphemeralWorkspace(
                run_id=data["run_id"],
                space_key=data["space_key"],
                mode=data["mode"],
                root_page_title=data["root_page_title"],
                root_page_id=data.get("root_page_id"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _clear_session(self) -> None:
        path = self._session_path()
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Space lifecycle (Confluence REST v1)
    # ------------------------------------------------------------------

    def _create_private_space(self, run_id: str) -> str:
        space_key = f"CS{run_id.upper()}"
        payload = {
            "key": space_key,
            "name": f"Confluence Sync Smoke {run_id}",
        }
        url = f"{self.wiki_base}/rest/api/space/_private"
        resp = requests.post(
            url, json=payload, auth=self.auth, timeout=self.timeout,
        )
        if resp.status_code == 403:
            url = f"{self.wiki_base}/rest/api/space"
            resp = requests.post(
                url, json=payload, auth=self.auth, timeout=self.timeout,
            )
        if resp.status_code not in (200, 201):
            raise SmokeProvisionError(
                f"POST space failed ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        key = data.get("key") or space_key
        return str(key)

    def _delete_space(self, space_key: str) -> None:
        url = f"{self.wiki_base}/rest/api/space/{space_key}"
        resp = requests.delete(url, auth=self.auth, timeout=self.timeout)
        if resp.status_code == 404:
            print(f"  ⚠ Space {space_key} already gone")
            return
        if resp.status_code not in (200, 202, 204):
            raise SmokeProvisionError(
                f"DELETE space {space_key} failed ({resp.status_code}): {resp.text[:300]}"
            )
        if resp.status_code == 202:
            try:
                data = resp.json()
                status_path = (data.get("_links") or {}).get("status")
                if status_path:
                    self._poll_long_task(status_path)
            except Exception as exc:
                print(f"  ⚠ Space delete scheduled; poll skipped: {exc}")

    def _poll_long_task(self, status_path: str, timeout: int = 180) -> None:
        if status_path.startswith("http"):
            url = status_path
        elif status_path.startswith("/"):
            url = f"{self.base_url.rstrip('/wiki')}{status_path}"
        else:
            url = f"{self.wiki_base}/rest/api/{status_path.lstrip('/')}"

        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(url, auth=self.auth, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            finished = data.get("finished", False)
            successful = data.get("successful", True)
            if finished:
                if not successful:
                    raise SmokeProvisionError(f"Long task failed: {data}")
                return
            time.sleep(2)
        print("  ⚠ Space delete still running (long task timeout)")

    def _delete_ephemeral_root(self, ws: EphemeralWorkspace) -> None:
        from confluence_sync.smoke_cleanup import SmokeCleanup

        cleanup = SmokeCleanup(
            base_url=self.base_url,
            username=self.auth.username,
            token=self.auth.password,
            space_key=ws.space_key,
            root_page_id=ws.root_page_id,
        )
        if ws.root_page_id:
            cleanup.delete_subtree_including_root(ws.root_page_id)
            return

        page_id = cleanup.find_page_by_title(ws.root_page_title)
        if page_id:
            cleanup.delete_subtree_including_root(page_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fallback_space_key(self) -> str:
        import os

        for var in ("CONFLUENCE_SMOKE_FALLBACK_SPACE", "CONFLUENCE_SPACE"):
            value = os.getenv(var, "").strip()
            if value:
                return value
        raise SmokeProvisionError(
            "Cannot create ephemeral space and no fallback space configured. "
            "Set CONFLUENCE_SMOKE_FALLBACK_SPACE or CONFLUENCE_SPACE in "
            "~/.local/confluence-sync/.env"
        )

    @staticmethod
    def _patch_dest(dest: Dict[str, Any], ws: EphemeralWorkspace) -> Dict[str, Any]:
        patched = copy.deepcopy(dest)
        patched["confluence"]["space_key"] = ws.space_key
        patched["confluence"]["root_page_title"] = ws.root_page_title
        patched["confluence"]["root_page_id"] = ws.root_page_id
        return patched

    def record_root_page_id(self, workspace: EphemeralWorkspace, root_page_id: str) -> None:
        """Persist root page id for fallback teardown."""
        if workspace.mode != "ephemeral_root":
            return
        updated = EphemeralWorkspace(
            run_id=workspace.run_id,
            space_key=workspace.space_key,
            mode=workspace.mode,
            root_page_title=workspace.root_page_title,
            root_page_id=str(root_page_id),
        )
        self._save_session(updated)
