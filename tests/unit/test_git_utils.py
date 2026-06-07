"""Unit tests for git_utils.py — path resolution and GitHub URL building."""

from __future__ import annotations

import subprocess

from confluence_sync.git_utils import (
    _normalise_remote_url,
    get_file_github_url,
    get_repo_root,
    resolve_git_root_for_file,
)

# ---------------------------------------------------------------------------
# _normalise_remote_url
# ---------------------------------------------------------------------------


def test_normalise_https():
    url = "https://github.com/org/repo.git"
    assert _normalise_remote_url(url) == "https://github.com/org/repo"


def test_normalise_ssh():
    url = "git@github.com:org/repo.git"
    assert _normalise_remote_url(url) == "https://github.com/org/repo"


def test_normalise_non_github_returns_none():
    url = "git@gitlab.com:org/repo.git"
    assert _normalise_remote_url(url) is None


def test_normalise_https_no_dot_git():
    url = "https://github.com/org/repo"
    assert _normalise_remote_url(url) == "https://github.com/org/repo"


# ---------------------------------------------------------------------------
# get_repo_root
# ---------------------------------------------------------------------------


def test_get_repo_root_finds_dotgit(tmp_path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    result = get_repo_root(sub)
    assert result == tmp_path


def test_get_repo_root_not_in_repo(tmp_path):
    result = get_repo_root(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# resolve_git_root_for_file
# ---------------------------------------------------------------------------


def test_resolve_git_root_explicit(tmp_path):
    explicit = tmp_path / "myrepo"
    explicit.mkdir()
    result = resolve_git_root_for_file(
        tmp_path / "some_file.md",
        folder_git_root=explicit,
    )
    assert result == explicit.resolve()


def test_resolve_git_root_autodetect(tmp_path):
    (tmp_path / ".git").mkdir()
    file_path = (tmp_path / "docs" / "page.md")
    file_path.parent.mkdir()
    file_path.touch()
    result = resolve_git_root_for_file(file_path.resolve())
    assert result == tmp_path.resolve()


def test_resolve_git_root_fallback_project_root(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = tmp_path / "external" / "file.md"
    file_path.parent.mkdir()
    file_path.touch()
    result = resolve_git_root_for_file(file_path, project_root=project_root)
    assert result == project_root


# ---------------------------------------------------------------------------
# get_file_github_url
# ---------------------------------------------------------------------------


def test_get_file_github_url_no_path_segments(tmp_path):
    """URL must not contain /../ segments."""
    # Set up a real git repo with a remote
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test-org/test-repo.git"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "page.md"
    page.write_text("# Page\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
    )

    url = get_file_github_url(page, repo_root=tmp_path)
    assert url is not None
    assert "/../" not in url
    assert "github.com/test-org/test-repo" in url
    assert "docs/page.md" in url


def test_get_file_github_url_github_repo_override(tmp_path):
    override = "https://github.com/custom-org/custom-repo"
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True
    )
    page = tmp_path / "page.md"
    page.write_text("# Page\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
    )

    url = get_file_github_url(page, repo_root=tmp_path, github_repo_override=override)
    assert url is not None
    assert "custom-org/custom-repo" in url


def test_get_file_github_url_outside_repo_returns_none(tmp_path):
    file_path = tmp_path / "external.md"
    file_path.touch()
    result = get_file_github_url(file_path)
    assert result is None
