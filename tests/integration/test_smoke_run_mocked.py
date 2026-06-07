"""Mocked smoke run pipeline — provision → sync → verify → patch → teardown."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from confluence_sync.commands.smoke import _smoke_run
from confluence_sync.report_generator import SyncResult
from confluence_sync.smoke_provision import EphemeralWorkspace


def _fake_args(tmp_path: Path) -> MagicMock:
    repo_root = Path(__file__).resolve().parents[2]
    config = repo_root / "tests" / "live_smoke" / "confluence-sync.yml"
    args = MagicMock()
    args.destination = "smoke-live"
    args.project_root = None
    args.config = str(config)
    args.state_dir = str(tmp_path / "state")
    return args


@pytest.fixture
def smoke_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_TOKEN", "test-token")


def test_smoke_run_step_order(tmp_path: Path, smoke_env: None) -> None:
    events: List[str] = []
    sync_call = {"n": 0}

    ws = EphemeralWorkspace(
        run_id="abc12345",
        space_key="CSABC12345",
        mode="ephemeral_space",
        root_page_title="Smoke Root abc12345",
    )
    patched_dest: Dict[str, Any] = {
        "name": "Smoke",
        "confluence": {
            "url": "https://example.atlassian.net",
            "space_key": ws.space_key,
            "root_page_title": ws.root_page_title,
            "root_page_id": None,
        },
        "source": {"folders": [{"path": "docs"}]},
        "credentials": {"username": "u@e.com", "token_env_var": "CONFLUENCE_TOKEN"},
        "options": {},
    }

    baseline_results = [
        SyncResult("docs/index.md", "docs", "created", page_id="1"),
        SyncResult("docs/sibling.md", "docs", "created", page_id="2"),
    ]
    skipped_results = [
        SyncResult("docs/index.md", "docs", "skipped", page_id="1"),
        SyncResult("docs/sibling.md", "docs", "skipped", page_id="2"),
    ]
    patch_results = [
        SyncResult("docs/index.md", "docs", "skipped", page_id="1"),
        SyncResult("docs/sibling.md", "docs", "updated", page_id="2"),
    ]

    def fake_provision(_dest: Dict[str, Any]) -> tuple[Dict[str, Any], EphemeralWorkspace]:
        events.append("provision")
        return patched_dest, ws

    def fake_sync(**_kwargs: Any) -> List[SyncResult]:
        sync_call["n"] += 1
        if sync_call["n"] == 1:
            events.append("clean_sync")
            return baseline_results
        if sync_call["n"] == 2:
            events.append("incremental_sync")
            return skipped_results
        events.append("patch_sync")
        return patch_results

    def fake_verify_all(_state: Dict[str, Any], _root: Path) -> None:
        events.append("verify")

    def fake_destroy(_workspace: EphemeralWorkspace | None) -> None:
        events.append("teardown")

    provisioner = MagicMock()
    provisioner.provision.side_effect = fake_provision
    provisioner.destroy_workspace.side_effect = fake_destroy
    provisioner.record_root_page_id = MagicMock()

    with (
        patch("confluence_sync.smoke_provision.SmokeProvisioner.from_destination", return_value=provisioner),
        patch("confluence_sync.sync.sync_destination", side_effect=fake_sync),
        patch("confluence_sync.smoke_verify.SmokeVerify.from_destination") as verify_cls,
        patch("confluence_sync.smoke_cleanup.SmokeCleanup.from_destination"),
        patch("confluence_sync.sync_state.load_sync_state") as load_state,
    ):
        verify_cls.return_value.verify_all.side_effect = fake_verify_all
        load_state.return_value = {
            "sync_history": {
                "docs/index.md": {"page_id": "1", "page_title": "Index"},
                "docs/sibling.md": {"page_id": "2", "page_title": "Sibling"},
            },
            "root_page_id": "root-1",
        }

        rc = _smoke_run(_fake_args(tmp_path))

    assert rc == 0
    assert events == [
        "provision",
        "clean_sync",
        "verify",
        "incremental_sync",
        "patch_sync",
        "verify",
        "teardown",
    ]
