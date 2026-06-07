"""
Sync orchestration for Confluence Sync.

Orchestrates the full sync pipeline:
1. Phase 1: Prepare content locally (no API calls)
2. Phase 2a: Create folders (parallelized by depth level)
3. Phase 2b: Sync pages (parallel with configurable thread count)
4. Phase 3: Detect and delete orphaned pages/folders

This module was adapted from sync-to-confluence.py.
See ADR 0013 (parallel folder sync) and ADR 0016 (project-local paths).
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from confluence_sync.attachment_handler import AttachmentHandler
from confluence_sync.config import ConfigError, resolve_credentials
from confluence_sync.confluence_sync import (
    ConfluenceSync,
)
from confluence_sync.content_preparer import ContentPreparer, PreparedContent
from confluence_sync.git_utils import (
    get_current_commit_hash,
    get_github_repo_url,
)
from confluence_sync.orphan_handler import OrphanHandler
from confluence_sync.paths import destination_state_dir, mermaid_cache_dir, resolve_state_dir  # noqa: F401
from confluence_sync.report_generator import SyncResult, generate_sync_report, save_report_to_file
from confluence_sync.sync_state import (
    compact_sync_state,
    compute_content_hash,
    find_by_signature,
    get_page_history,
    load_sync_state,
    update_destination_metadata,
    update_page_history,
)


@dataclass
class SyncContext:
    """Runtime context threaded through all sync phases."""
    project_root: Path
    config_path: Optional[Path]
    state_dir: Path
    user_dir: Path


class ProgressTracker:
    """Track and display sync progress."""

    def __init__(self, total_steps: int = 0):
        self.total_steps = total_steps
        self.current_step = 0
        self.step_names: List[str] = []
        self.step_totals: Dict[str, int] = {}
        self.step_current: Dict[str, int] = {}

    def add_step(self, name: str, total: int = 0) -> None:
        self.step_names.append(name)
        self.step_totals[name] = total
        self.step_current[name] = 0

    def start_step(self, name: str) -> None:
        if name in self.step_names:
            self.current_step = self.step_names.index(name) + 1
            print(f"\n[{self.current_step}/{len(self.step_names)}] {name}")

    def update_step(
        self,
        name: str,
        current: int,
        total: Optional[int] = None,
        show_every: int = 1,
        current_file: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        if name not in self.step_current:
            return
        self.step_current[name] = current
        if total is not None:
            self.step_totals[name] = total
        total_count = self.step_totals.get(name, 0)
        if total_count > 0:
            should_show = (
                (current % show_every == 0)
                or (current == total_count)
                or (current == 1)
                or (total_count < 50)
            )
            if should_show:
                percent = int((current / total_count) * 100)
                bar_length = 40
                filled = int(bar_length * current / total_count)
                bar = "█" * filled + "░" * (bar_length - filled)
                file_info = ""
                if current_file:
                    file_display = current_file if len(current_file) <= 40 else "..." + current_file[-37:]
                    status_indicator = ""
                    if status:
                        if status == "skipped":
                            status_indicator = " [no-change-skipped]"
                        elif status in ["created", "updated"]:
                            status_indicator = " [changed]"
                    file_info = f" | {file_display}{status_indicator}"
                print(
                    f"\r  [{bar}] {current}/{total_count} ({percent}%){file_info}",
                    end="",
                    flush=True,
                )

    def complete_step(self, name: str) -> None:
        if name in self.step_current:
            total = self.step_totals.get(name, 0)
            current = self.step_current.get(name, 0)
            if total > 0:
                bar = "█" * 40
                print(f"\r  [{bar}] {current}/{total} (100%) ✓")
            else:
                print("  ✓ Complete")
            print()


def sync_destination(
    destination_id: str,
    destination_config: Dict[str, Any],
    project_root: Path,
    state_dir: Optional[Path] = None,
    dry_run_override: Optional[bool] = None,
    cache_prepared: bool = False,
    force_update: bool = False,
    scope_folder: Optional[str] = None,
) -> List[SyncResult]:
    """
    Sync a destination to Confluence.

    Args:
        destination_id: Unique identifier for this destination
        destination_config: Configuration dictionary for this destination
        project_root: Root path of the Git repository
        state_dir: Optional explicit state directory (defaults to project-local)
        dry_run_override: Override dry_run setting from config
        cache_prepared: If True, cache prepared content to disk for debugging
        force_update: If True, force update all pages even if content unchanged
        scope_folder: Sync only this folder and its descendants (path relative to project root)

    Returns:
        List of SyncResult objects for each synced file
    """
    from confluence_sync.paths import resolve_state_dir as _resolve_state_dir

    results: List[SyncResult] = []

    destination_name = destination_config["name"]
    confluence_config = destination_config["confluence"]
    source_config = destination_config["source"]
    options = destination_config.get("options", {})

    try:
        creds = resolve_credentials(destination_config)
    except ConfigError as e:
        print(f"ERROR: {e}")
        return results

    dry_run = dry_run_override if dry_run_override is not None else options.get("dry_run", False)
    add_git_metadata = options.get("add_git_metadata", False)
    github_repo_override = options.get("github_repo_override")
    parallel_threads = options.get("parallel_threads", 5)

    # Resolve state dir
    if state_dir is None:
        state_dir = _resolve_state_dir(project_root)
    dest_state_dir = destination_state_dir(state_dir, destination_id)

    repo_commit_hash = get_current_commit_hash(project_root) if add_git_metadata else None
    github_repo_url = get_github_repo_url(project_root, github_repo_override) if add_git_metadata else None

    sync_state = load_sync_state(destination_id, dest_state_dir.parent)
    cache_dir = mermaid_cache_dir()

    base_url = confluence_config["url"]
    space_key = confluence_config["space_key"]
    root_page_title = confluence_config["root_page_title"]
    root_page_id = confluence_config.get("root_page_id")

    print(f"\n{'='*80}")
    print(f"Syncing destination: {destination_name} ({destination_id})")
    print(f"Space: {space_key}")
    print(f"Root page: {root_page_title}")
    if dry_run:
        print("DRY RUN MODE - No changes will be made")
    print(f"{'='*80}")
    print(f"  State dir: {dest_state_dir}")
    print(f"  Mermaid PNG cache: {cache_dir}")
    print()

    try:
        confluence_sync_client = ConfluenceSync(base_url, creds["username"], creds["token"], space_key)
    except Exception as e:
        print(f"ERROR: Could not initialize Confluence client: {e}")
        return results

    if dry_run:
        print("\n[DRY RUN] Preparing content without syncing...")
        preparer = ContentPreparer(
            repo_root=project_root,
            github_repo_url=github_repo_url,
            add_git_metadata=add_git_metadata,
            attachment_handler=None,
            confluence_base_url=confluence_sync_client.base_url,
            mermaid_cache_dir=cache_dir,
        )

        all_prepared: List[PreparedContent] = []
        all_folder_pages: List[Dict[str, Any]] = []

        for folder_config in source_config["folders"]:
            folder_path = project_root / folder_config["path"]
            source_folder_id = folder_config["path"]
            if not folder_path.exists():
                continue
            folder_prepared, _, folder_directory_pages = preparer.prepare_directory_content(
                directory=folder_path,
                parent_id=root_page_id,
                root_path=folder_path,
                source_folder=source_folder_id,
                destination_id=destination_id,
                sync_state=sync_state,
                files_processed_count=[0],
                prepared_contents=[],
                parent_id_map={},
                directory_pages=[],
            )
            all_prepared.extend(folder_prepared)
            all_folder_pages.extend(folder_directory_pages)

        print(f"\n✓ Prepared {len(all_prepared)} files and {len(all_folder_pages)} folders")
        print("="*80)
        return results

    # --- Live sync ---
    try:
        total_files = sum(
            len(list((project_root / fc["path"]).rglob("*.md")))
            for fc in source_config["folders"]
            if (project_root / fc["path"]).exists()
        )

        progress = ProgressTracker()
        progress.add_step("Finding/Creating root page", 1)
        progress.add_step("Preparing content", total_files)
        progress.add_step("Creating folders", 0)
        progress.add_step("Syncing files", total_files)

        attachment_handler = AttachmentHandler(confluence_sync_client)

        preparer = ContentPreparer(
            repo_root=project_root,
            github_repo_url=github_repo_url,
            add_git_metadata=add_git_metadata,
            attachment_handler=attachment_handler,
            confluence_base_url=confluence_sync_client.base_url,
            mermaid_cache_dir=cache_dir,
        )

        # Find or create root page
        progress.start_step("Finding/Creating root page")

        if not root_page_id:
            metadata_file = dest_state_dir / "sync-metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)
                        root_page_id = metadata.get("root_page_id")
                except Exception:
                    pass

        if root_page_id:
            try:
                confluence_sync_client._make_request("GET", f"/pages/{root_page_id}")
                root_parent_id = root_page_id
                print(f"Found root page: {root_page_title} (ID: {root_parent_id})")
            except Exception:
                print(f"⚠ Root page (ID: {root_page_id}) not found, will create new one...")
                root_parent_id = None
        else:
            root_parent_id = None

        if not root_parent_id:
            homepage_id = confluence_sync_client.get_space_homepage_id()
            if not homepage_id:
                raise Exception("Could not get space homepage ID.")

            root_file_key = f"__root__{root_page_title}"
            root_prev_history = get_page_history(destination_id, dest_state_dir.parent, root_file_key, None)
            root_content = f"# {root_page_title}\n\n*Root page for synced documentation*"
            root_storage, _ = preparer.markdown_to_storage_format(root_content, None, project_root, None)
            root_hash = compute_content_hash(root_storage)

            root_parent_id, root_status, _, _ = confluence_sync_client.find_or_create_page(
                file_path=root_file_key,
                title=root_page_title,
                title_original=root_page_title,
                storage_format=root_storage,
                content_hash=root_hash,
                parent_id=homepage_id,
                sync_state_entry=root_prev_history,
                root_page_id=None,
            )
            print(f"Root page: {root_page_title} (ID: {root_parent_id}) - {root_status}")

        progress.complete_step("Finding/Creating root page")

        update_destination_metadata(
            destination_id,
            state_dir,
            confluence_space=space_key,
            root_page_id=root_parent_id,
            commit_hash=repo_commit_hash if add_git_metadata else None,
        )

        # Build link cache from sync state
        file_to_title: Dict[str, str] = {}
        file_to_page_id: Dict[str, str] = {}

        if sync_state and "sync_history" in sync_state:
            for file_path, page_entry in sync_state["sync_history"].items():
                if isinstance(page_entry, dict):
                    page_id = page_entry.get("page_id")
                    page_title = page_entry.get("page_title")
                    if page_id and page_title:
                        normalized_path = file_path
                        for fc in source_config["folders"]:
                            prefix = fc["path"] + "/"
                            if file_path.startswith(prefix):
                                normalized_path = file_path[len(prefix):]
                                break
                        file_to_page_id[normalized_path] = str(page_id)
                        file_to_title[normalized_path] = page_title

        preparer.file_to_title = file_to_title
        preparer.file_to_page_id = file_to_page_id

        # Pre-scan directories to populate preparer.file_to_title for all discovered files
        for folder_config in source_config["folders"]:
            folder_path = project_root / folder_config["path"]
            if folder_path.exists():
                preparer.pre_scan_titles(
                    directory=folder_path,
                    root_path=folder_path,
                    source_folder=folder_config["path"]
                )

        # Phase 1: Prepare all content
        progress.start_step("Preparing content")
        all_prepared: List[PreparedContent] = []
        all_folder_pages: List[Dict[str, Any]] = []
        files_processed = [0]

        def prep_progress(count: int, filename: str) -> None:
            progress.update_step("Preparing content", count, total_files, show_every=5, current_file=filename)

        for folder_config in source_config["folders"]:
            folder_path = project_root / folder_config["path"]
            source_folder_id = folder_config["path"]
            if not folder_path.exists():
                print(f"  ⚠ Folder not found: {folder_path}")
                continue

            fp, _, fdir = preparer.prepare_directory_content(
                directory=folder_path,
                parent_id=root_parent_id,
                root_path=folder_path,
                source_folder=source_folder_id,
                commit_hash=repo_commit_hash if add_git_metadata else None,
                destination_id=destination_id,
                sync_state=sync_state,
                files_processed_count=files_processed,
                prepared_contents=[],
                parent_id_map={},
                progress_callback=prep_progress,
                directory_pages=[],
            )
            all_prepared.extend(fp)
            all_folder_pages.extend(fdir)

        # Apply scope filter
        if scope_folder:
            scope_prefix = scope_folder.strip("/")
            if scope_prefix:
                all_prepared = [
                    p for p in all_prepared
                    if p.file_key == scope_prefix or p.file_key.startswith(scope_prefix + "/")
                ]
                all_folder_pages = [
                    f for f in all_folder_pages
                    if (
                        f.get("folder_key", "") == scope_prefix
                        or f.get("folder_key", "").startswith(scope_prefix + "/")
                        or scope_prefix.startswith(f.get("folder_key", "") + "/")
                    )
                ]

        progress.complete_step("Preparing content")
        print(f"  Prepared {len(all_prepared)} files, {len(all_folder_pages)} folders")

        # Phase 2a: Create folders (depth-ordered, parallelized within each level)
        progress.start_step("Creating folders")
        parent_id_map: Dict[str, str] = {}
        folders_by_depth: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

        for folder_info in all_folder_pages:
            depth = folder_info["dir_rel_path"].count("/") if folder_info["dir_rel_path"] != "." else 0
            folders_by_depth[depth].append(folder_info)

        folder_lock = threading.Lock()
        discovered_folders: set = set()

        for depth in sorted(folders_by_depth.keys()):
            depth_folders = folders_by_depth[depth]

            def create_folder(fi: Dict[str, Any]) -> None:
                dir_rel_path = fi["dir_rel_path"]
                folder_title = fi["folder_title"]
                parent_id_val = fi["parent_id"]
                source_folder = fi.get("source_folder")
                folder_key = fi.get("folder_key", dir_rel_path)
                prev_history = fi.get("prev_history")

                with folder_lock:
                    from pathlib import Path as P
                    if dir_rel_path and dir_rel_path != ".":
                        ppath = P(dir_rel_path).parent
                        parent_rel = str(ppath) if str(ppath) != "." else ""
                        parent_folder_key = f"{source_folder}/{parent_rel}" if (source_folder and parent_rel) else parent_rel
                        if parent_folder_key and parent_folder_key in parent_id_map:
                            parent_id_val = parent_id_map[parent_folder_key]

                try:
                    from confluence_sync.sync_state import append_folder_history
                    if prev_history and prev_history.get("folder_id"):
                        folder_id = prev_history["folder_id"]
                        folder_status = "found"
                    else:
                        folder_id, folder_status = confluence_sync_client.create_folder(
                            title=folder_title,
                            space_id=confluence_sync_client.space_id,
                            parent_id=parent_id_val or root_parent_id,
                            root_page_id=root_parent_id,
                        )
                        if folder_status == "title_conflict":
                            raise Exception(
                                f"Title conflict: folder '{folder_title}' already exists elsewhere in the space"
                            )

                    with folder_lock:
                        parent_id_map[folder_key] = folder_id
                        discovered_folders.add(folder_key)

                    append_folder_history(
                        destination_id,
                        state_dir,
                        folder_path=dir_rel_path,
                        source_folder=source_folder,
                        folder_id=folder_id,
                        folder_title=folder_title,
                        parent_id=parent_id_val or root_parent_id,
                        status=folder_status,
                    )
                except Exception as e:
                    print(f"  ✗ Error creating folder '{folder_title}': {e}")

            max_workers = min(8, len(depth_folders))
            if max_workers > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(create_folder, fi) for fi in depth_folders]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"  ✗ Folder error: {e}")
            else:
                for fi in depth_folders:
                    create_folder(fi)

        progress.complete_step("Creating folders")

        # Update parent IDs for prepared content
        for prepared in all_prepared:
            dir_rel = getattr(prepared, "_dir_rel_path", None)
            if dir_rel:
                source_folder = prepared.source_folder
                folder_key = f"{source_folder}/{dir_rel}" if source_folder and dir_rel != source_folder else dir_rel
                if folder_key in parent_id_map:
                    prepared.parent_id = parent_id_map[folder_key]

        # Phase 2b: Sync pages in parallel
        progress.start_step("Syncing files")
        discovered_files: set = set()
        renamed_files: set = set()
        page_lock = threading.Lock()
        pages_done = [0]

        def sync_page(prepared: PreparedContent) -> SyncResult:
            file_key = prepared.file_key
            with page_lock:
                discovered_files.add(file_key)

            try:
                prev = prepared.prev_history
                content_hash = prepared.content_hash

                # Check rename
                if not prev and prepared.content_signature:
                    rename_entry = find_by_signature(sync_state, prepared.content_signature, file_key)
                    if rename_entry:
                        with page_lock:
                            renamed_files.add(rename_entry["old_path"])
                        prepared.renamed_from = rename_entry["old_path"]
                        prev = rename_entry

                # Check skip
                if not force_update and prev and prev.get("content_hash") == content_hash and prev.get("page_id"):
                    update_page_history(
                        destination_id,
                        state_dir,
                        file_path=prepared.file_key,
                        source_folder=None,
                        page_id=prev.get("page_id"),
                        page_title=prev.get("page_title"),
                        commit_hash=prepared.commit_hash,
                        sync_status="skipped",
                        content_hash=content_hash,
                        version=prev.get("version"),
                        parent_id=prepared.parent_id,
                        content_signature=prepared.content_signature,
                    )
                    return SyncResult(
                        file_path=prepared.rel_path,
                        source_folder=prepared.source_folder,
                        status="skipped",
                        page_id=prev.get("page_id"),
                        page_title=prev.get("page_title"),
                        new_commit=prepared.commit_hash,
                        content_hash=content_hash,
                    )

                # Sync to Confluence
                page_id, sync_status, version, actual_title = confluence_sync_client.find_or_create_page(
                    file_path=file_key,
                    title=prepared.title,
                    title_original=prepared.title,
                    storage_format=prepared.storage_format,
                    content_hash=content_hash,
                    parent_id=prepared.parent_id or root_parent_id,
                    sync_state_entry=prev,
                    root_page_id=root_parent_id,
                )

                # Upload attachments
                if prepared.image_paths and attachment_handler:
                    for img_path in prepared.image_paths:
                        attachment_handler.upload_attachment(page_id, img_path)

                if prepared.mermaid_attachments and attachment_handler:
                    for fname, png_bytes in prepared.mermaid_attachments:
                        attachment_handler.upload_attachment_from_bytes(page_id, fname, png_bytes)

                update_page_history(
                    destination_id,
                    state_dir,
                    file_path=prepared.file_key,
                    source_folder=None,
                    page_id=page_id,
                    page_title=actual_title,
                    commit_hash=prepared.commit_hash,
                    sync_status=sync_status,
                    content_hash=content_hash,
                    version=version,
                    parent_id=prepared.parent_id,
                    content_signature=prepared.content_signature,
                )

                confluence_url = f"{confluence_sync_client.base_url}/pages/viewpage.action?pageId={page_id}"
                return SyncResult(
                    file_path=prepared.rel_path,
                    source_folder=prepared.source_folder,
                    status=sync_status,
                    page_id=page_id,
                    page_title=actual_title,
                    confluence_url=confluence_url,
                    github_url=prepared.github_url,
                    new_commit=prepared.commit_hash,
                    content_hash=content_hash,
                )
            except Exception as e:
                return SyncResult(
                    file_path=prepared.rel_path,
                    source_folder=prepared.source_folder,
                    status="error",
                    error_message=str(e),
                )

        with ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            futures = {executor.submit(sync_page, p): p for p in all_prepared}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    with page_lock:
                        pages_done[0] += 1
                        progress.update_step(
                            "Syncing files",
                            pages_done[0],
                            len(all_prepared),
                            show_every=1,
                            current_file=futures[future].rel_path,
                            status=result.status,
                        )
                except Exception as e:
                    prepared = futures[future]
                    results.append(
                        SyncResult(
                            file_path=prepared.rel_path,
                            source_folder=prepared.source_folder,
                            status="error",
                            error_message=str(e),
                        )
                    )

        progress.complete_step("Syncing files")

        # Phase 3: Orphan detection (skip if scoped)
        if not scope_folder:
            print("\nChecking for orphaned pages/folders...")
            orphan_handler = OrphanHandler(confluence_sync_client)
            orphan_pages, orphan_folders = orphan_handler.find_orphans(
                sync_state=sync_state,
                discovered_files=discovered_files,
                renamed_files=renamed_files,
                discovered_folders=discovered_folders,
            )

            if orphan_pages or orphan_folders:
                print(f"  Found {len(orphan_pages)} orphaned pages, {len(orphan_folders)} orphaned folders")
                orphan_handler.delete_orphans(orphan_pages, orphan_folders)
            else:
                print("  No orphans found")

        # Compact state
        compact_sync_state(destination_id, dest_state_dir.parent)

        # Generate report
        sync_state_final = load_sync_state(destination_id, dest_state_dir.parent)
        report_text = generate_sync_report(
            destination_id=destination_id,
            destination_name=destination_name,
            sync_state=sync_state_final,
            current_commit=repo_commit_hash,
            results=results,
            confluence_base_url=confluence_sync_client.base_url,
            space_key=space_key,
        )
        report_file = save_report_to_file(destination_id, report_text, dest_state_dir.parent)
        print(f"\n✓ Report saved: {report_file}")

        # Print summary
        created = sum(1 for r in results if r.status == "created")
        updated = sum(1 for r in results if r.status == "updated")
        skipped = sum(1 for r in results if r.status == "skipped")
        errors = sum(1 for r in results if r.status == "error")
        print(f"\nSync complete: {created} created, {updated} updated, {skipped} skipped, {errors} errors")
        if errors:
            for result in results:
                if result.status == "error":
                    msg = result.error_message or "unknown error"
                    print(f"  ✗ {result.file_path}: {msg}")

    except Exception as e:
        print(f"\n✗ Sync failed: {e}")
        raise

    return results
