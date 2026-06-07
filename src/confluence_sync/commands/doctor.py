"""doctor subcommand — pre-flight checks."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Optional


def run_doctor(args: argparse.Namespace) -> int:
    """Entry point for `confluence-sync doctor`."""
    from confluence_sync.config import ConfigError, get_destination, load_destination_config
    from confluence_sync.paths import ProjectRootError, SyncContext, user_local_dir

    issues: list[str] = []
    ok: list[str] = []

    # --- Python version ---
    if sys.version_info >= (3, 11):
        ok.append(f"Python {sys.version.split()[0]}")
    else:
        issues.append(f"Python {sys.version.split()[0]} — requires 3.11+")

    # --- Project root ---
    try:
        ctx = SyncContext.from_args(
            project_root_arg=args.project_root,
            config_arg=args.config,
            state_dir_arg=args.state_dir,
        )
        ok.append(f"Project root: {ctx.project_root}")
        ok.append(f"Config:       {ctx.config_path}")
        ok.append(f"State dir:    {ctx.state_dir}")
    except (ProjectRootError, FileNotFoundError) as exc:
        issues.append(str(exc))
        _print_report(ok, issues)
        return 1

    # --- Config load ---
    try:
        config = load_destination_config(ctx.config_path, ctx.project_root)
        ok.append(f"Config valid ({len(config.get('destinations', []))} destinations)")
    except Exception as exc:
        issues.append(f"Config invalid: {exc}")
        _print_report(ok, issues)
        return 1

    # --- CONFLUENCE_TOKEN ---
    dest_id: Optional[str] = getattr(args, "destination", None)
    if dest_id:
        try:
            dest = get_destination(config, dest_id)
            token_env_var = dest["credentials"]["token_env_var"]
            if os.getenv(token_env_var):
                ok.append(f"Token env '{token_env_var}' is set")
            else:
                issues.append(
                    f"Token env '{token_env_var}' not found. "
                    f"Add to ~/.local/confluence-sync/.env: {token_env_var}=your-token"
                )
        except ConfigError as exc:
            issues.append(str(exc))
    else:
        # Check all destinations
        for dest in config.get("destinations", []):
            token_var = dest.get("credentials", {}).get("token_env_var", "")
            if token_var and not os.getenv(token_var):
                issues.append(f"Token '{token_var}' (dest: {dest.get('id')}) not set")
        if not issues:
            ok.append("All token env vars present")

    # --- Source folders ---
    for dest in config.get("destinations", []):
        if dest_id and dest.get("id") != dest_id:
            continue
        for folder in dest.get("source", {}).get("folders", []):
            fp = ctx.project_root / folder["path"]
            if fp.exists():
                ok.append(f"Source folder exists: {folder['path']}")
            else:
                issues.append(f"Source folder missing: {folder['path']} (dest: {dest.get('id')})")

    # --- Mermaid ---
    has_mermaid = shutil.which("mmdc") is not None
    if not has_mermaid:
        # Try npx
        try:
            subprocess.run(
                ["npx", "--yes", "@mermaid-js/mermaid-cli", "--version"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            has_mermaid = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if has_mermaid:
        ok.append("Mermaid CLI available (mmdc or npx)")
    else:
        issues.append(
            "Mermaid CLI not found — diagram rendering will fail.\n"
            "  Install: npm install -g @mermaid-js/mermaid-cli"
        )

    # --- User global dir ---
    uld = user_local_dir()
    ok.append(f"User local dir: {uld} ({'exists' if uld.exists() else 'will be created on first use'})")

    _print_report(ok, issues)
    return 1 if issues else 0


def _print_report(ok: list[str], issues: list[str]) -> None:
    print("\n── doctor ──────────────────────────────────────────────")
    for item in ok:
        print(f"  ✓  {item}")
    for item in issues:
        print(f"  ✗  {item}")
    print("────────────────────────────────────────────────────────")
    if issues:
        print(f"\n{len(issues)} issue(s) found — fix above before syncing.")
    else:
        print("\nAll checks passed.")
