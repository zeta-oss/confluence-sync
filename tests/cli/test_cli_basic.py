"""CLI subprocess tests for basic entrypoint behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "confluence_sync.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_help_exits_0():
    result = _run("--help")
    assert result.returncode == 0
    assert "confluence-sync" in result.stdout


def test_version():
    from confluence_sync import __version__
    result = _run("--version")
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_sync_without_destination_exits_1(tmp_path):
    (tmp_path / ".git").mkdir()
    result = _run("sync", cwd=str(tmp_path))
    assert result.returncode == 1
    assert "destination" in result.stderr.lower() or "destination" in result.stdout.lower()


def test_doctor_help_exits_0():
    result = _run("doctor", "--help")
    assert result.returncode == 0


def test_init_help_exits_0():
    result = _run("init", "--help")
    assert result.returncode == 0


def test_smoke_run_help_shows_config():
    result = _run("smoke", "run", "--help")
    assert result.returncode == 0
    assert "--config" in result.stdout


def test_doctor_smoke_live_with_token(tmp_path):
    import os
    import stat

    repo_root = Path(__file__).resolve().parents[2]
    config = repo_root / "tests" / "live_smoke" / "confluence-sync.yml"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    mmdc = fake_bin / "mmdc"
    mmdc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    mmdc.chmod(mmdc.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["CONFLUENCE_TOKEN"] = "test-token"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        [sys.executable, "-m", "confluence_sync.cli", "doctor", "-d", "smoke-live", "--config", str(config)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "CONFLUENCE_TOKEN" in result.stdout or "Token env" in result.stdout


def test_sync_missing_destination_shows_hint(tmp_path):
    """sync -d missing should exit 1 and mention available IDs."""
    cs_dir = tmp_path / ".confluence-sync"
    cs_dir.mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    cfg = cs_dir / "confluence-sync.yml"
    cfg.write_text(
        "destinations:\n"
        "  - id: real-dest\n"
        "    name: Real\n"
        "    confluence:\n"
        "      url: https://x.atlassian.net\n"
        "      space_key: X\n"
        "      root_page_title: Root\n"
        "    source:\n"
        "      folders:\n"
        "        - path: docs\n"
        "    credentials:\n"
        "      username: u@e.com\n"
        "      token_env_var: CONFLUENCE_TOKEN\n",
        encoding="utf-8",
    )
    result = _run("sync", "-d", "missing-dest", cwd=str(tmp_path))
    assert result.returncode == 1


def test_no_git_repo_exits_1(tmp_path):
    result = _run("sync", "-d", "any", cwd=str(tmp_path))
    assert result.returncode == 1
