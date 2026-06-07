"""
confluence-sync CLI entry point.

Subcommands: sync, init, doctor, smoke
See ADR 0025 (env loading), ADR 0016 (project-local paths).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> None:
    """Main CLI entry point — routes to subcommand modules."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args) or 0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confluence-sync",
        description="Sync Markdown documentation to Confluence.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version()}",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ---- sync ----
    sync_p = sub.add_parser("sync", help="Sync one or all destinations to Confluence")
    sync_p.add_argument("-d", "--destination", metavar="ID", help="Destination ID to sync")
    sync_p.add_argument("--all", action="store_true", help="Sync all destinations")
    sync_p.add_argument("--dry-run", action="store_true", help="Prepare + validate only; no API writes")
    sync_p.add_argument("--force-update", action="store_true", help="Ignore content-hash skip")
    sync_p.add_argument("--folder", metavar="PATH", help="Partial sync; path relative to project root")
    sync_p.add_argument("--project-root", metavar="PATH", help="Git repo root (default: cwd walk-up)")
    sync_p.add_argument("--config", metavar="PATH", help="Config file override")
    sync_p.add_argument("--state-dir", metavar="PATH", help="State directory override")
    sync_p.add_argument("--cache-prepared", action="store_true", help="Debug: write prepared HTML to state dir")
    sync_p.set_defaults(func=_cmd_sync)

    # ---- init ----
    init_p = sub.add_parser("init", help="Scaffold .confluence-sync/ in the current project")
    init_p.add_argument("--project-root", metavar="PATH", help="Git repo root")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing config")
    init_p.set_defaults(func=_cmd_init)

    # ---- doctor ----
    doc_p = sub.add_parser("doctor", help="Run pre-flight checks")
    doc_p.add_argument("-d", "--destination", metavar="ID", help="Check specific destination")
    doc_p.add_argument("--project-root", metavar="PATH", help="Git repo root")
    doc_p.add_argument("--config", metavar="PATH", help="Config file override")
    doc_p.add_argument("--state-dir", metavar="PATH", help="State directory override")
    doc_p.set_defaults(func=_cmd_doctor)

    # ---- smoke ----
    smoke_p = sub.add_parser("smoke", help="Live smoke testing (release gate)")
    smoke_sub = smoke_p.add_subparsers(dest="smoke_action", metavar="<action>")

    for action in ("reset", "run", "verify"):
        sp = smoke_sub.add_parser(action, help=f"smoke {action}")
        sp.add_argument("-d", "--destination", metavar="ID", required=True)
        sp.add_argument("--project-root", metavar="PATH")
        sp.add_argument("--config", metavar="PATH", help="Config file override")
        sp.add_argument("--state-dir", metavar="PATH")
        sp.set_defaults(func=_cmd_smoke)

    return parser


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_sync(args: argparse.Namespace) -> int:
    from confluence_sync.commands.sync import run_sync
    return run_sync(args)


def _cmd_init(args: argparse.Namespace) -> int:
    from confluence_sync.commands.init import run_init
    return run_init(args)


def _cmd_doctor(args: argparse.Namespace) -> int:
    from confluence_sync.commands.doctor import run_doctor
    return run_doctor(args)


def _cmd_smoke(args: argparse.Namespace) -> int:
    from confluence_sync.commands.smoke import run_smoke
    return run_smoke(args)


def _version() -> str:
    from confluence_sync import __version__
    return __version__


if __name__ == "__main__":  # pragma: no cover
    main()
