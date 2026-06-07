"""init subcommand — scaffold .confluence-sync/ in a project."""

from __future__ import annotations

import argparse
import sys

_EXAMPLE_CONFIG = """\
# confluence-sync.yml
# Sync Markdown documentation to Confluence.
# Run 'confluence-sync doctor' to validate before first sync.

destinations:
  - id: my-destination
    name: My Documentation
    confluence:
      url: https://your-org.atlassian.net
      space_key: MYSPACE
      root_page_title: My Docs Root
      root_page_id: null   # optional: pin to a specific page ID
    source:
      folders:
        - path: docs
          create_root_parent: true
          # title: Custom Folder Title  # optional
    credentials:
      username: your@email.com
      token_env_var: CONFLUENCE_TOKEN   # set in ~/.local/confluence-sync/.env
    options:
      add_git_metadata: true
      github_repo_override: null
      dry_run: false
      parallel_threads: 5
"""

_GITIGNORE_ENTRY = "destinations/\n"


def run_init(args: argparse.Namespace) -> int:
    """Entry point for `confluence-sync init`."""
    from confluence_sync.paths import ProjectRootError, resolve_project_root

    try:
        root = resolve_project_root(args.project_root)
    except ProjectRootError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    cs_dir = root / ".confluence-sync"
    config_path = cs_dir / "confluence-sync.yml"
    gitignore_path = cs_dir / ".gitignore"

    # Create .confluence-sync/
    cs_dir.mkdir(exist_ok=True)

    # Write config
    if config_path.exists() and not args.force:
        print(f"Config already exists: {config_path}")
        print("Use --force to overwrite.")
    else:
        config_path.write_text(_EXAMPLE_CONFIG, encoding="utf-8")
        print(f"✓ Created: {config_path}")

    # Write .gitignore
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if "destinations/" not in content:
            gitignore_path.write_text(content + _GITIGNORE_ENTRY, encoding="utf-8")
            print(f"✓ Updated: {gitignore_path}")
        else:
            print("  (gitignore already has destinations/ entry)")
    else:
        gitignore_path.write_text(_GITIGNORE_ENTRY, encoding="utf-8")
        print(f"✓ Created: {gitignore_path}")

    print("\nNext steps:")
    print(f"  1. Edit {config_path}")
    print("  2. Add your token: echo 'CONFLUENCE_TOKEN=...' >> ~/.local/confluence-sync/.env")
    print("  3. Run: confluence-sync doctor")
    print("  4. Run: confluence-sync sync -d my-destination")
    return 0
