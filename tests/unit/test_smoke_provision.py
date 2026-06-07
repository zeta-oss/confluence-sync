"""Unit tests for ephemeral smoke workspace provisioning."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from confluence_sync.smoke_provision import EphemeralWorkspace, SmokeProvisioner


@pytest.fixture
def provisioner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SmokeProvisioner:
    monkeypatch.setattr(
        "confluence_sync.smoke_provision.user_local_dir",
        lambda: tmp_path,
    )
    return SmokeProvisioner(
        "https://example.atlassian.net",
        "user@example.com",
        "token",
    )


def test_provision_ephemeral_space(provisioner: SmokeProvisioner) -> None:
    dest = {
        "confluence": {
            "url": "https://example.atlassian.net",
            "space_key": "ephemeral",
            "root_page_title": "Smoke",
            "root_page_id": None,
        },
        "credentials": {"username": "user@example.com", "token_env_var": "CONFLUENCE_TOKEN"},
        "options": {"auto_provision_space": True},
    }

    with patch.object(provisioner, "_create_private_space", return_value="CSABCDEF12"):
        patched, ws = provisioner.provision(dest)

    assert ws.mode == "ephemeral_space"
    assert ws.space_key == "CSABCDEF12"
    assert patched["confluence"]["space_key"] == "CSABCDEF12"
    assert patched["confluence"]["root_page_id"] is None
    session = json.loads((provisioner._session_path()).read_text(encoding="utf-8"))
    assert session["space_key"] == "CSABCDEF12"


def test_provision_fallback_space(provisioner: SmokeProvisioner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_SPACE", "~personal")
    dest = {
        "confluence": {
            "url": "https://example.atlassian.net",
            "space_key": "ephemeral",
            "root_page_title": "Smoke",
            "root_page_id": None,
        },
        "credentials": {"username": "user@example.com", "token_env_var": "CONFLUENCE_TOKEN"},
        "options": {"auto_provision_space": True},
    }

    with patch.object(provisioner, "_create_private_space", side_effect=RuntimeError("denied")):
        patched, ws = provisioner.provision(dest)

    assert ws.mode == "ephemeral_root"
    assert ws.space_key == "~personal"
    assert patched["confluence"]["root_page_title"].startswith("Smoke Root ")


def test_destroy_ephemeral_space(provisioner: SmokeProvisioner) -> None:
    ws = EphemeralWorkspace(
        run_id="abc12345",
        space_key="CSABC12345",
        mode="ephemeral_space",
        root_page_title="Smoke Root abc12345",
    )
    provisioner._save_session(ws)

    with patch.object(provisioner, "_delete_space") as delete_space:
        provisioner.destroy_workspace(ws)

    delete_space.assert_called_once_with("CSABC12345")
    assert not provisioner._session_path().exists()


def test_patch_fixture_mapping(provisioner: SmokeProvisioner, tmp_path: Path) -> None:
    mapping = tmp_path / ".confluence-mapping.yaml"
    mapping.write_text(
        'pages:\n  index.md: "Smoke Test - Index"\n',
        encoding="utf-8",
    )
    provisioner.patch_fixture_mapping(tmp_path, "deadbeef")
    text = mapping.read_text(encoding="utf-8")
    assert 'Smoke deadbeef - Index"' in text
