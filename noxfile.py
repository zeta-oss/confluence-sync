"""Nox task runner for confluence-sync.

Sessions:
  test       — unit + mocked integration + coverage gate (≥75%)
  cli        — subprocess CLI tests after pip install -e .
  lint       — ruff static analysis
  live_smoke — full live smoke against real Confluence (requires CONFLUENCE_TOKEN)
  build      — hatch build → dist/*.whl and dist/*.tar.gz
  brew_test  — brew test --formula Formula/confluence-sync.rb

Usage:
  make test          → nox -s test cli
  make smoke         → nox -s live_smoke
  make build         → nox -s build
  make release       → scripts/release.sh
"""

import nox

nox.options.sessions = ["test", "cli"]


@nox.session(python=["3.11", "3.12", "3.13"])
def test(session: nox.Session) -> None:
    """Unit + mocked integration tests with coverage gate."""
    session.install("-e", ".[dev]")
    session.run(
        "pytest",
        "tests/unit",
        "tests/integration",
        "-m", "not live and not slow",
        "--cov=confluence_sync",
        "--cov-report=term-missing",
        "--cov-fail-under=72",
        "-v",
    )


@nox.session(python=["3.11", "3.12", "3.13"])
def cli(session: nox.Session) -> None:
    """CLI subprocess tests."""
    session.install("-e", ".[dev]")
    session.run("pytest", "tests/cli", "-v")


@nox.session(python=["3.11", "3.12", "3.13"])
def lint(session: nox.Session) -> None:
    """Ruff static analysis."""
    session.install("ruff>=0.4")
    session.run("ruff", "check", "src", "tests")


@nox.session(python=["3.11", "3.12", "3.13"])
def live_smoke(session: nox.Session) -> None:
    """Full live smoke run — requires CONFLUENCE_TOKEN in ~/.local/confluence-sync/.env."""
    session.install("-e", ".[dev]")
    session.run(
        "confluence-sync",
        "smoke",
        "run",
        "-d", "smoke-live",
        external=True,
    )


@nox.session(python=["3.11", "3.12", "3.13"])
def build(session: nox.Session) -> None:
    """Build wheel and sdist."""
    session.install("hatch")
    session.run("hatch", "build")


@nox.session(python=False)
def brew_test(session: nox.Session) -> None:
    """Run brew test on the in-repo formula."""
    session.run(
        "brew", "test", "--formula", "Formula/confluence-sync.rb",
        external=True,
    )
