"""smoke subcommand — live release verification (clean + incremental + media + links)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


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


def _load_smoke_dest(args: argparse.Namespace) -> tuple[Any, Dict[str, Any]]:
    from confluence_sync.paths import SyncContext
    from confluence_sync.config import load_destination_config, get_destination

    ctx = SyncContext.from_args(
        project_root_arg=getattr(args, "project_root", None),
        config_arg=getattr(args, "config", None),
        state_dir_arg=getattr(args, "state_dir", None),
    )
    config = load_destination_config(ctx.config_path, ctx.project_root)
    dest = get_destination(config, args.destination)
    return ctx, dest


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def _smoke_reset(args: argparse.Namespace) -> int:
    """Destroy any ephemeral workspace from the last smoke run."""
    from confluence_sync.paths import ProjectRootError
    from confluence_sync.smoke_provision import SmokeProvisioner

    try:
        _, dest = _load_smoke_dest(args)
    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("── smoke reset ──")
    SmokeProvisioner.from_destination(dest).destroy_session_workspace()
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _smoke_run(args: argparse.Namespace) -> int:
    """Full smoke sequence: provision workspace → sync → verify → destroy."""
    from confluence_sync.paths import ProjectRootError
    from confluence_sync.sync import sync_destination
    from confluence_sync.smoke_cleanup import SmokeCleanup
    from confluence_sync.smoke_verify import SmokeVerify
    from confluence_sync.smoke_provision import SmokeProvisioner, EphemeralWorkspace

    fixture_dir = Path(__file__).parent.parent.parent.parent / "tests" / "live_smoke" / "fixture"
    if not fixture_dir.exists():
        print(f"Smoke fixture not found: {fixture_dir}", file=sys.stderr)
        return 1

    ws_tmp = Path(tempfile.mkdtemp(prefix="smoke-workspace-"))
    state_tmp = Path(tempfile.mkdtemp(prefix="smoke-state-"))
    workspace: Optional[EphemeralWorkspace] = None
    provisioner: Optional[SmokeProvisioner] = None
    dest: Optional[Dict[str, Any]] = None

    try:
        _, base_dest = _load_smoke_dest(args)
        provisioner = SmokeProvisioner.from_destination(base_dest)

        print("── smoke provision ──")
        dest, workspace = provisioner.provision(base_dest)

        shutil.copytree(str(fixture_dir), str(ws_tmp), dirs_exist_ok=True)
        if workspace.mode != "ephemeral_space":
            provisioner.patch_fixture_mapping(ws_tmp, workspace.run_id)

        subprocess.run(["git", "init"], cwd=ws_tmp, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=ws_tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "smoke baseline"],
            cwd=ws_tmp, check=True, capture_output=True,
        )

        cleanup = SmokeCleanup.from_destination(dest)
        cleanup.wipe_local_state(state_tmp, args.destination)

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

        from confluence_sync.sync_state import load_sync_state

        state = load_sync_state(args.destination, state_tmp)
        root_page_id = state.get("root_page_id")
        if root_page_id and workspace and provisioner:
            provisioner.record_root_page_id(workspace, str(root_page_id))

        print("── smoke verify (clean) ──")
        verifier = SmokeVerify.from_destination(dest)
        verifier.verify_all(state, ws_tmp)

        print("── smoke: incremental (expect all skipped) ──")
        results2 = sync_destination(
            destination_id=args.destination,
            destination_config=dest,
            project_root=ws_tmp,
            state_dir=state_tmp,
        )
        created2 = [r for r in results2 if r.status == "created"]
        if created2:
            print(f"  ✗ Incremental run created {len(created2)} pages (expected 0)", file=sys.stderr)
            return 1
        updated2 = [r for r in results2 if r.status == "updated"]
        if updated2:
            print(f"  ℹ {len(updated2)} page(s) updated (link normalization); re-running incremental...")
            results2b = sync_destination(
                destination_id=args.destination,
                destination_config=dest,
                project_root=ws_tmp,
                state_dir=state_tmp,
            )
            if any(r.status in ("created", "updated") for r in results2b):
                n = sum(1 for r in results2b if r.status in ("created", "updated"))
                print(f"  ✗ Second incremental run changed {n} pages (expected 0)", file=sys.stderr)
                return 1
            print("  ✓ Second incremental run: all pages skipped")
        else:
            print("  ✓ Incremental run: all pages skipped")

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

        state_after = load_sync_state(args.destination, state_tmp)
        verifier.verify_all(state_after, ws_tmp)

        print("\n✓ Smoke run passed")
        return 0

    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"  ✗ Smoke run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        print("── smoke teardown ──")
        try:
            if provisioner is not None:
                provisioner.destroy_workspace(workspace)
        except Exception as exc:
            print(f"  ⚠ Teardown error: {exc}")
        shutil.rmtree(ws_tmp, ignore_errors=True)
        shutil.rmtree(state_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def _smoke_verify(args: argparse.Namespace) -> int:
    """API assertions only — no content creation."""
    from confluence_sync.paths import ProjectRootError
    from confluence_sync.smoke_verify import SmokeVerify
    from confluence_sync.sync_state import load_sync_state

    try:
        ctx, dest = _load_smoke_dest(args)
    except (ProjectRootError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    verifier = SmokeVerify.from_destination(dest)
    state = load_sync_state(args.destination, ctx.state_dir)
    verifier.verify_all(state, ctx.project_root)
    return 0
