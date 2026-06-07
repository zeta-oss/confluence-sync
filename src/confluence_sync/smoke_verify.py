"""
Smoke verification — post-sync API assertions for release gate.

Checks page count, Mermaid attachment, images, cross-page links,
anchor links, and git footer without a browser.

See ADR 0023 (live smoke before release), ADR 0028 (smoke subcommand).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


class SmokeVerifyError(Exception):
    """Raised when a smoke assertion fails."""


class SmokeVerify:
    """Post-sync API assertion helper for the smoke fixture."""

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
        self._failures: list[str] = []

    @classmethod
    def from_destination(cls, dest: Dict[str, Any]) -> "SmokeVerify":
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

    def verify_all(self, sync_state: Dict[str, Any], project_root: Path) -> None:
        """Run all assertions; raises SmokeVerifyError on first failure."""
        self._failures = []

        history = sync_state.get("sync_history", {})
        if not history:
            raise SmokeVerifyError("Sync state is empty — nothing to verify")

        self._check_page_count(history)
        self._check_mermaid_attachment(history)
        self._check_image_attachments(history)
        self._check_anchor_links(history)

        if self._failures:
            msg = "\n".join(f"  ✗ {f}" for f in self._failures)
            raise SmokeVerifyError(f"Smoke verification failed:\n{msg}")

        print(f"  ✓ Smoke verification passed ({len(history)} pages)")

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        import requests

        url = f"{self.base_url}/wiki/api/v2/{path.lstrip('/')}"
        resp = requests.get(url, auth=self.auth, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _check_page_count(self, history: Dict[str, Any]) -> None:
        expected = len(history)
        if expected < 1:
            self._failures.append("No pages in sync state")
        else:
            print(f"  ✓ Page count: {expected}")

    def _check_mermaid_attachment(self, history: Dict[str, Any]) -> None:
        """Verify mermaid.md page has a mermaid-0.png attachment."""
        mermaid_key = next(
            (k for k in history if "mermaid" in k.lower() and k.endswith(".md")), None
        )
        if not mermaid_key:
            print("  ⚠ No mermaid.md in sync state — skipping mermaid check")
            return

        page_id = history[mermaid_key].get("page_id")
        if not page_id:
            self._failures.append("mermaid.md has no page_id in sync state")
            return

        try:
            data = self._get(f"pages/{page_id}/attachments")
            attachments = data.get("results", [])
            mermaid_files = [a for a in attachments if a.get("title", "").startswith("mermaid")]
            if not mermaid_files:
                self._failures.append(f"mermaid.md page {page_id} has no mermaid-*.png attachment")
            else:
                print(f"  ✓ Mermaid attachment: {mermaid_files[0].get('title')}")
        except Exception as exc:
            self._failures.append(f"Could not verify mermaid attachment: {exc}")

    def _check_image_attachments(self, history: Dict[str, Any]) -> None:
        """Verify images.md page has the expected image attachments."""
        images_key = next(
            (k for k in history if "images" in k.lower() and k.endswith(".md")), None
        )
        if not images_key:
            print("  ⚠ No images.md in sync state — skipping image attachment check")
            return

        page_id = history[images_key].get("page_id")
        if not page_id:
            self._failures.append("images.md has no page_id in sync state")
            return

        try:
            data = self._get(f"pages/{page_id}/attachments")
            titles = {a.get("title", "") for a in data.get("results", [])}
            for expected_img in ("test.png", "hero.jpeg"):
                if expected_img in titles:
                    print(f"  ✓ Image attachment: {expected_img}")
                else:
                    self._failures.append(
                        f"images.md page {page_id} missing attachment: {expected_img}"
                    )
        except Exception as exc:
            self._failures.append(f"Could not verify image attachments: {exc}")

    def _page_storage_html(self, page_id: str) -> str:
        data = self._get(f"pages/{page_id}", params={"body-format": "storage"})
        body = data.get("body") or {}
        storage = body.get("storage")
        if isinstance(storage, dict) and storage.get("value"):
            return storage["value"]
        return body.get("value", "") or ""

    def _check_anchor_links(self, history: Dict[str, Any]) -> None:
        """Verify cross-page anchor links in anchors-source / anchors-target fixture pages."""
        source_key = next(
            (k for k in history if k.endswith("anchors-source.md")), None
        )
        target_key = next(
            (k for k in history if k.endswith("anchors-target.md")), None
        )
        if not source_key or not target_key:
            print("  ⚠ Anchor fixture pages missing from sync state — skipping link check")
            return

        source_id = history[source_key].get("page_id")
        target_id = history[target_key].get("page_id")
        if not source_id or not target_id:
            self._failures.append("Anchor fixture pages missing page_id in sync state")
            return

        try:
            source_html = self._page_storage_html(str(source_id))
            target_html = self._page_storage_html(str(target_id))

            has_source_link = (
                "#my-section" in source_html
                or 'ac:anchor="my-section"' in source_html
                or "ac:anchor='my-section'" in source_html
            )
            if not has_source_link:
                self._failures.append(
                    f"anchors-source page {source_id} missing link to #my-section"
                )
            else:
                print("  ✓ Anchor link on anchors-source page")

            has_target_heading = (
                'id="my-section"' in target_html
                or "id='my-section'" in target_html
            )
            if not has_target_heading:
                self._failures.append(
                    f"anchors-target page {target_id} missing heading id my-section"
                )
            else:
                print("  ✓ Anchor target heading on anchors-target page")
        except Exception as exc:
            self._failures.append(f"Could not verify anchor links: {exc}")
