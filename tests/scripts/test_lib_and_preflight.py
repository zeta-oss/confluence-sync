"""Shell script integration tests via pytest subprocess (L2)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_SH = REPO_ROOT / "scripts" / "lib.sh"
PREFLIGHT_SH = REPO_ROOT / "scripts" / "release-preflight.sh"


def _bash(cmd: str, *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=merged,
        cwd=str(cwd or REPO_ROOT),
    )


def _stub_venv(root: Path) -> Path:
    bin_dir = root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    python_stub = bin_dir / "python"
    python_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_stub.chmod(0o755)
    log = root / "cli-log.txt"
    cli = bin_dir / "confluence-sync"
    cli.write_text(
        f"""#!/bin/bash
echo "$@" >> "{log}"
exit 0
""",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    return log


def _write_smoke_pass(home: Path, sha: str, *, hours_ago: float = 0) -> None:
    ts = datetime.now(timezone.utc)
    if hours_ago:
        from datetime import timedelta

        ts = ts - timedelta(hours=hours_ago)
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = home / ".local" / "confluence-sync" / "smoke-last-pass"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timestamp": stamp, "sha": sha}) + "\n", encoding="utf-8")


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    shutil.copytree(REPO_ROOT / "tests" / "live_smoke", repo / "tests" / "live_smoke")
    _stub_venv(repo)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "stub"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.mark.scripts
def test_run_live_smoke_uses_venv_cli(fake_repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    log = fake_repo / "cli-log.txt"
    cmd = f"""
set -euo pipefail
source "{LIB_SH}"
export REPO_ROOT="{fake_repo}"
export HOME="{home}"
export CONFLUENCE_TOKEN=test-token
run_live_smoke
"""
    result = _bash(cmd)
    assert result.returncode == 0, result.stderr
    log_text = log.read_text(encoding="utf-8")
    assert "smoke run" in log_text
    assert "-d smoke-live" in log_text
    assert "tests/live_smoke/confluence-sync.yml" in log_text


@pytest.mark.scripts
def test_run_smoke_reset_uses_venv_cli(fake_repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    log = fake_repo / "cli-log.txt"
    cmd = f"""
set -euo pipefail
source "{LIB_SH}"
export REPO_ROOT="{fake_repo}"
export HOME="{home}"
export CONFLUENCE_TOKEN=test-token
run_smoke_reset
"""
    result = _bash(cmd)
    assert result.returncode == 0, result.stderr
    log_text = log.read_text(encoding="utf-8")
    assert "smoke reset" in log_text


@pytest.mark.scripts
def test_preflight_without_smoke_pass_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "HOME": str(home),
        "REPO_ROOT": str(REPO_ROOT),
        "CONFLUENCE_TOKEN": "test-token",
    }
    result = subprocess.run(
        ["bash", str(PREFLIGHT_SH)],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1
    assert "Run: make smoke" in result.stderr


@pytest.mark.scripts
def test_preflight_stale_session_invokes_reset(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    session_dir = home / ".local" / "confluence-sync"
    session_dir.mkdir(parents=True)
    (session_dir / "smoke-session.json").write_text('{"run_id":"deadbeef"}', encoding="utf-8")

    head_sha = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    _write_smoke_pass(home, head_sha)

    cli = REPO_ROOT / ".venv" / "bin" / "confluence-sync"
    backup = tmp_path / "confluence-sync.bak"
    shutil.copy(cli, backup)
    log = tmp_path / "cli-log.txt"
    cli.write_text(
        f"""#!/bin/bash
echo "$@" >> "{log}"
exit 0
""",
        encoding="utf-8",
    )
    cli.chmod(cli.stat().st_mode | 0o111)

    env = {
        "HOME": str(home),
        "CONFLUENCE_TOKEN": "test-token",
    }
    try:
        result = subprocess.run(
            ["bash", str(PREFLIGHT_SH)],
            capture_output=True,
            text=True,
            env={**os.environ, **env},
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "smoke reset" in log.read_text(encoding="utf-8")
    finally:
        shutil.copy(backup, cli)
        cli.chmod(cli.stat().st_mode | 0o111)


@pytest.mark.scripts
def test_preflight_wrong_sha_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write_smoke_pass(home, "0" * 40)

    env = {
        "HOME": str(home),
        "REPO_ROOT": str(REPO_ROOT),
        "CONFLUENCE_TOKEN": "test-token",
    }
    result = subprocess.run(
        ["bash", str(PREFLIGHT_SH)],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1
    assert "Re-run: make smoke" in result.stderr


@pytest.mark.scripts
def test_preflight_legacy_timestamp_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = home / ".local" / "confluence-sync"
    path.mkdir(parents=True)
    (path / "smoke-last-pass").write_text("2026-06-07T12:00:00Z\n", encoding="utf-8")

    env = {
        "HOME": str(home),
        "REPO_ROOT": str(REPO_ROOT),
        "CONFLUENCE_TOKEN": "test-token",
    }
    result = subprocess.run(
        ["bash", str(PREFLIGHT_SH)],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1
    assert "Legacy smoke-last-pass" in result.stderr or "Re-run: make smoke" in result.stderr
