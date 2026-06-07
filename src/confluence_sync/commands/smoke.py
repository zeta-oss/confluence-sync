"""smoke subcommand — live release verification (clean + incremental + media + links)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_smoke(args: argparse.Namespace) -> int:
    """Entry point for `confluence-sync smoke reset|run|verify`."""
    action = getattr(args, "smoke_action", None)
    if action == "reset":
        return _smoke_reset(args)
    elif action == "run":
        return _smoke_run(args)
    elif action == "verify":
        return _smoke_verify(args)
    else:
        print("Usage: confluence-sync smoke <reset|run|verify> -d DESTINATION", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def _smoke_reset(args: argparse.Namespace) -> int:
    """Delete all child pages under smoke root and wipe local state."""
    from confluence_sync.paths import SyncContext, ProjectRootError
    from confluence_sync.config import load_destination_config, get_destination
    from confluence_sync.smoke_cleanup import SmokeCleanup

    try:
        ctx = SyncContext.from_args(
            project_root_arg=getattr(args, "project_root", None),
            state_dir_arg=getattr(args, "state_dir", None),
        )
    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    config = load_destination_config(ctx.config_path, ctx.project_root)
    dest = get_destination(config, args.destination)

    cleanup = SmokeCleanup.from_destination(dest)
    cleanup.reset(ctx.state_dir, args.destination)
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _smoke_run(args: argparse.Namespace) -> int:
    """Full smoke sequence: copy fixture → reset → clean sync → verify → incremental → verify → teardown."""
    from confluence_sync.paths import SyncContext, ProjectRootError
    from confluence_sync.config import load_destination_config, get_destination
    from confluence_sync.sync import sync_destination
    from confluence_sync.smoke_cleanup import SmokeCleanup
    from confluence_sync.smoke_verify import SmokeVerify

    fixture_dir = Path(__file__).parent.parent.parent.parent / "tests" / "live_smoke" / "fixture"
    if not fixture_dir.exists():
        print(f"Smoke fixture not found: {fixture_dir}", file=sys.stderr)
        return 1

    ws_tmp = Path(tempfile.mkdtemp(prefix="smoke-workspace-"))
    state_tmp = Path(tempfile.mkdtemp(prefix="smoke-state-"))

    try:
        ctx = SyncContext.from_args(
            project_root_arg=getattr(args, "project_root", None),
        )
        config = load_destination_config(ctx.config_path, ctx.project_root)
        dest = get_destination(config, args.destination)
        cleanup = SmokeCleanup.from_destination(dest)

        # Step 0: copy fixture to tmp
        shutil.copytree(str(fixture_dir), str(ws_tmp), dirs_exist_ok=True)
        subprocess.run(["git", "init"], cwd=ws_tmp, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=ws_tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "smoke baseline"],
            cwd=ws_tmp, check=True, capture_output=True,
        )

        # Step 1: reset
        print("── smoke reset ──")
        cleanup.reset(state_tmp, args.destination)

        # Step 2: clean sync
        print("── smoke: clean sync ──")
        results = sync_destination(
            destination_id=args.destination,
            destination_config=dest,
            project_root=ws_tmp,
            state_dir=state_tmp,
        )
        errors = [r for r in results if r.status == "error"]
        if errors:
            print(f"  ✗ {len(errors)} errors in clean sync", file=sys.stderr)
            return 1

        # Step 3: verify
        print("── smoke verify (clean) ──")
        verifier = SmokeVerify.from_destination(dest)
        from confluence_sync.sync_state import load_sync_state
        state = load_sync_state(args.destination, state_tmp)
        verifier.verify_all(state, ws_tmp)

        # Step 4: incremental (no-op)
        print("── smoke: incremental (expect all skipped) ──")
        results2 = sync_destination(
            destination_id=args.destination,
            destination_config=dest,
            project_root=ws_tmp,
            state_dir=state_tmp,
        )
        updated = [r for r in results2 if r.status in ("created", "updated")]
        if updated:
            print(f"  ✗ Incremental run created/updated {len(updated)} pages (expected 0)", file=sys.stderr)
            return 1

        # Step 5: content change
        print("── smoke: incremental update ──")
        sibling = ws_tmp / "docs" / "sibling.md"
        sentinel = "\n\n<!-- smoke-sentinel -->\n"
        sibling.write_text(sibling.read_text(encoding="utf-8") + sentinel, encoding="utf-8")
        subprocess.run(["git", "add", "docs/sibling.md"], cwd=ws_tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "smoke patch sibling"],
            cwd=ws_tmp, check=True, capture_output=True,
        )
        results3 = sync_destination(
            destination_id=args.destination,
            destination_config=dest,
            project_root=ws_tmp,
            state_dir=state_tmp,
        )
        updated3 = [r for r in results3 if r.status == "updated"]
        if len(updated3) != 1:
            print(f"  ✗ Expected exactly 1 updated, got {len(updated3)}", file=sys.stderr)
            return 1
        print(f"  ✓ Exactly 1 updated: {updated3[0].file_path}")

        # Step 6: verify links after update
        state_after = load_sync_state(args.destination, state_tmp)
        verifier.verify_all(state_after, ws_tmp)

        print("\n✓ Smoke run passed")
        return 0

    except Exception as exc:
        print(f"  ✗ Smoke run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        # Always teardown
        print("── smoke teardown ──")
        try:
            from confluence_sync.paths import SyncContext
            ctx2 = SyncContext.from_args(project_root_arg=getattr(args, "project_root", None))
            config2 = load_destination_config(ctx2.config_path, ctx2.project_root)
            dest2 = get_destination(config2, args.destination)
            SmokeCleanup.from_destination(dest2).reset(state_tmp, args.destination)
        except Exception as exc:
            print(f"  ⚠ Teardown error: {exc}")
        shutil.rmtree(ws_tmp, ignore_errors=True)
        shutil.rmtree(state_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def _smoke_verify(args: argparse.Namespace) -> int:
    """API assertions only — no content creation."""
    from confluence_sync.paths import SyncContext, ProjectRootError
    from confluence_sync.config import load_destination_config, get_destination
    from confluence_sync.smoke_verify import SmokeVerify
    from confluence_sync.sync_state import load_sync_state

    try:
        ctx = SyncContext.from_args(
            project_root_arg=getattr(args, "project_root", None),
            state_dir_arg=getattr(args, "state_dir", None),
        )
    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    config = load_destination_config(ctx.config_path, ctx.project_root)
    dest = get_destination(config, args.destination)
    verifier = SmokeVerify.from_destination(dest)
    state = load_sync_state(args.destination, ctx.state_dir)
    verifier.verify_all(state, ctx.project_root)
    return 0
