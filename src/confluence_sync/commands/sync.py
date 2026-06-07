"""sync subcommand — orchestrates per-destination Confluence sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def run_sync(args: argparse.Namespace) -> int:
    """Entry point for `confluence-sync sync`."""
    from confluence_sync.paths import SyncContext, ProjectRootError
    from confluence_sync.config import load_destination_config, get_destination, list_destination_ids, ConfigError
    from confluence_sync.sync import sync_destination

    if not args.destination and not args.all:
        print(
            "Error: specify a destination with -d/--destination or use --all\n"
            "Usage: confluence-sync sync -d DESTINATION_ID",
            file=sys.stderr,
        )
        return 1

    try:
        ctx = SyncContext.from_args(
            project_root_arg=args.project_root,
            config_arg=args.config,
            state_dir_arg=args.state_dir,
        )
    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        config = load_destination_config(ctx.config_path, ctx.project_root)
    except Exception as exc:
        print(f"Error loading config: {exc}", file=sys.stderr)
        return 1

    if args.all:
        dest_ids = list_destination_ids(config)
        if not dest_ids:
            print("No destinations found in config.", file=sys.stderr)
            return 1
    else:
        try:
            get_destination(config, args.destination)  # validate
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        dest_ids = [args.destination]

    has_errors = False
    for dest_id in dest_ids:
        dest_config = get_destination(config, dest_id)
        try:
            results = sync_destination(
                destination_id=dest_id,
                destination_config=dest_config,
                project_root=ctx.project_root,
                state_dir=ctx.state_dir,
                dry_run_override=True if args.dry_run else None,
                cache_prepared=args.cache_prepared,
                force_update=args.force_update,
                scope_folder=args.folder,
            )
            errors = [r for r in results if r.status == "error"]
            if errors:
                has_errors = True
        except Exception as exc:
            print(f"Sync failed for '{dest_id}': {exc}", file=sys.stderr)
            has_errors = True

    return 2 if has_errors else 0
