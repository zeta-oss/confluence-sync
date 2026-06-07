"""
CLI subprocess tests.

Tests the installed confluence-sync entrypoint via subprocess.
"""

from __future__ import annotations

import subprocess
import sys


def run_cli(*args, cwd=None, env=None):
    """Run confluence_sync.cli as a module (works without install)."""
    return subprocess.run(
        [sys.executable, "-m", "confluence_sync.cli"] + list(args),
        capture_output=True, text=True, cwd=cwd, env=env,
    )


class TestCLIHelp:
    def test_help_exits_0(self):
        """confluence-sync --help exits 0."""
        result = run_cli("--help")
        assert result.returncode == 0
        assert "confluence-sync" in result.stdout.lower() or "sync" in result.stdout.lower()

    def test_version_exits_0(self):
        """confluence-sync --version exits 0."""
        from confluence_sync import __version__
        result = run_cli("--version")
        assert result.returncode == 0
        assert __version__ in result.stdout

    def test_sync_help(self):
        """confluence-sync sync --help exits 0."""
        result = run_cli("sync", "--help")
        assert result.returncode == 0


class TestCLISyncErrors:
    def test_sync_without_destination_exits_1(self, tmp_path):
        """confluence-sync sync without -d exits 1."""
        result = run_cli("sync", cwd=str(tmp_path))
        assert result.returncode == 1
        assert "destination" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_sync_outside_git_exits_1(self, tmp_path):
        """confluence-sync sync in non-git dir exits 1."""
        result = run_cli("sync", "-d", "test", cwd=str(tmp_path))
        assert result.returncode == 1

    def test_sync_missing_destination_exits_1(self, fake_project_root):
        """confluence-sync sync -d missing exits 1."""
        result = run_cli(
            "sync", "-d", "nonexistent-destination",
            cwd=str(fake_project_root),
        )
        assert result.returncode == 1

    def test_init_help_exits_0(self):
        """confluence-sync init --help exits 0."""
        result = run_cli("init", "--help")
        assert result.returncode == 0

    def test_doctor_help_exits_0(self):
        """confluence-sync doctor --help exits 0."""
        result = run_cli("doctor", "--help")
        assert result.returncode == 0

    def test_smoke_help_exits_0(self):
        """confluence-sync smoke --help exits 0."""
        result = run_cli("smoke", "--help")
        assert result.returncode == 0
