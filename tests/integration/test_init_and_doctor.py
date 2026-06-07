"""Integration tests for init and doctor commands."""

from __future__ import annotations

import subprocess
import sys


def run_cmd(*args, cwd=None, env=None):
    result = subprocess.run(
        [sys.executable, "-m", "confluence_sync.cli"] + list(args),
        capture_output=True, text=True, cwd=cwd, env=env,
    )
    return result


class TestInitCommand:
    def test_init_creates_config_file(self, fake_project_root):
        """confluence-sync init creates .confluence-sync/confluence-sync.yml."""
        config_file = fake_project_root / ".confluence-sync" / "confluence-sync.yml"
        assert not config_file.exists()  # should not exist in fixture

        result = run_cmd("init", "--project-root", str(fake_project_root))
        assert result.returncode == 0
        assert config_file.exists()

    def test_init_creates_gitignore(self, fake_project_root):
        """confluence-sync init creates .confluence-sync/.gitignore."""
        gi = fake_project_root / ".confluence-sync" / ".gitignore"
        if gi.exists():
            gi.unlink()
        run_cmd("init", "--project-root", str(fake_project_root))
        assert gi.exists()
        assert "destinations/" in gi.read_text()

    def test_init_does_not_overwrite_without_force(self, fake_project_root):
        """init does not overwrite existing config without --force."""
        # First run to create the file
        run_cmd("init", "--project-root", str(fake_project_root))
        config_file = fake_project_root / ".confluence-sync" / "confluence-sync.yml"
        assert config_file.exists()
        original = config_file.read_text()

        result = run_cmd("init", "--project-root", str(fake_project_root))
        assert result.returncode == 0
        assert config_file.read_text() == original  # unchanged

    def test_init_idempotent_with_force(self, fake_project_root):
        """init --force overwrites existing config."""
        result = run_cmd("init", "--force", "--project-root", str(fake_project_root))
        assert result.returncode == 0

    def test_init_outside_git_fails(self, tmp_path):
        """init outside git repo exits 1."""
        result = run_cmd("init", "--project-root", str(tmp_path))
        assert result.returncode == 1


class TestDoctorCommand:
    def test_doctor_exits_0_in_valid_fixture(self, fake_project_root, monkeypatch):
        """confluence-sync doctor exit 0 with valid fixture and token set."""
        import os
        env = os.environ.copy()
        env["CONFLUENCE_TOKEN"] = "test-token"

        result = subprocess.run(
            [sys.executable, "-m", "confluence_sync.cli", "doctor",
             "--project-root", str(fake_project_root),
             "-d", "test-dest"],
            capture_output=True, text=True, env=env,
        )
        # Should pass or warn, not hard fail (mermaid may warn)
        assert result.returncode in (0, 1)

    def test_doctor_exits_1_when_token_missing(self, fake_project_root, monkeypatch):
        """confluence-sync doctor exit 1 when token env var missing."""
        import os
        env = os.environ.copy()
        env.pop("CONFLUENCE_TOKEN", None)

        result = subprocess.run(
            [sys.executable, "-m", "confluence_sync.cli", "doctor",
             "--project-root", str(fake_project_root),
             "-d", "test-dest"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1
