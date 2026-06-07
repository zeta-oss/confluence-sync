"""
State management for per-destination Confluence sync (JSONL format).

JSONL allows streaming updates — each line is a separate JSON object.
See ADR 0005 (JSONL sync state), ADR 0016 (project-local paths).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Directory helpers  (state_dir comes from paths.resolve_state_dir)
# ---------------------------------------------------------------------------


def get_destination_data_dir(
    destination_id: str,
    state_dir: Path,
) -> Path:
    """Return (and create) the per-destination state subdirectory."""
    dest_dir = state_dir / destination_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


def get_state_file_path(destination_id: str, state_dir: Path) -> Path:
    return get_destination_data_dir(destination_id, state_dir) / "sync-state.jsonl"


def get_metadata_file_path(destination_id: str, state_dir: Path) -> Path:
    return get_destination_data_dir(destination_id, state_dir) / "sync-metadata.json"


# ---------------------------------------------------------------------------
# Load state
# ---------------------------------------------------------------------------


def load_sync_state(destination_id: str, state_dir: Path) -> Dict[str, Any]:
    """Load sync state (pages + folders) for a destination."""
    state_file = get_state_file_path(destination_id, state_dir)
    metadata_file = get_metadata_file_path(destination_id, state_dir)

    metadata: Dict[str, Any] = {
        "destination_id": destination_id,
        "last_sync_timestamp": None,
        "last_sync_commit": None,
        "confluence_space": None,
        "root_page_id": None,
    }

    if metadata_file.exists():
        try:
            with open(metadata_file, encoding="utf-8") as f:
                metadata.update(json.load(f))
        except Exception as exc:
            print(f"  ⚠ Warning: Error loading metadata: {exc}")

    sync_history: Dict[str, Any] = {}
    folders: Dict[str, Any] = {}

    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_type = entry.get("type", "page")
                        key = entry.get("file_path") or entry.get("folder_path")
                        if key:
                            if entry_type == "folder":
                                folders[key] = entry
                            else:
                                sync_history[key] = entry
                    except json.JSONDecodeError as exc:
                        print(f"  ⚠ Warning: Skipping invalid JSONL line {line_num}: {exc}")
        except OSError as exc:
            print(f"  ⚠ Warning: Error reading state file: {exc}")

    return {
        "destination_id": destination_id,
        "sync_history": sync_history,
        "folders": folders,
        **metadata,
    }


# ---------------------------------------------------------------------------
# Page history
# ---------------------------------------------------------------------------


def append_page_history(
    destination_id: str,
    state_dir: Path,
    file_path: str,
    source_folder: Optional[str] = None,
    page_id: Optional[str] = None,
    page_title: Optional[str] = None,
    page_title_original: Optional[str] = None,
    commit_hash: Optional[str] = None,
    sync_status: Optional[str] = None,
    content_hash: Optional[str] = None,
    version: Optional[int] = None,
    previous_commit: Optional[str] = None,
    previous_sync_date: Optional[str] = None,
    previous_content_hash: Optional[str] = None,
    parent_id: Optional[str] = None,
    previous_parent_id: Optional[str] = None,
    content_signature: Optional[str] = None,
) -> None:
    state_file = get_state_file_path(destination_id, state_dir)

    key = f"{source_folder}/{file_path}" if source_folder else file_path

    entry: Dict[str, Any] = {
        "file_path": key,
        "page_id": page_id,
        "page_title": page_title,
        "last_sync_commit": commit_hash,
        "last_sync_date": datetime.utcnow().isoformat() + "Z",
        "last_sync_status": sync_status,
        "content_hash": content_hash,
        "version": version,
    }

    if page_title_original:
        entry["page_title_original"] = page_title_original
    elif page_title:
        entry["page_title_original"] = page_title

    for k, v in (
        ("parent_id", parent_id),
        ("content_signature", content_signature),
        ("previous_commit", previous_commit),
        ("previous_sync_date", previous_sync_date),
        ("previous_content_hash", previous_content_hash),
        ("previous_parent_id", previous_parent_id),
    ):
        if v is not None:
            entry[k] = v

    try:
        with open(state_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"  ⚠ Warning: Could not append to state file: {exc}")


def get_page_history(
    destination_id: str,
    state_dir: Path,
    file_path: str,
    source_folder: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    state = load_sync_state(destination_id, state_dir)
    if source_folder:
        prefixed = f"{source_folder}/{file_path}"
        if prefixed in state["sync_history"]:
            return state["sync_history"][prefixed]
    return state["sync_history"].get(file_path)


def update_page_history(
    destination_id: str,
    state_dir: Path,
    file_path: str,
    source_folder: Optional[str] = None,
    **kwargs: Any,
) -> None:
    existing = get_page_history(destination_id, state_dir, file_path, source_folder) or {}
    merged = {**existing, **kwargs}
    append_page_history(
        destination_id,
        state_dir,
        file_path,
        source_folder=source_folder,
        page_id=merged.get("page_id"),
        page_title=merged.get("page_title"),
        page_title_original=merged.get("page_title_original"),
        commit_hash=merged.get("commit_hash") or merged.get("last_sync_commit"),
        sync_status=merged.get("sync_status") or merged.get("last_sync_status"),
        content_hash=merged.get("content_hash"),
        version=merged.get("version"),
        previous_commit=merged.get("previous_commit"),
        previous_sync_date=merged.get("previous_sync_date"),
        previous_content_hash=merged.get("previous_content_hash"),
        parent_id=merged.get("parent_id"),
        previous_parent_id=merged.get("previous_parent_id"),
        content_signature=merged.get("content_signature"),
    )


# ---------------------------------------------------------------------------
# Destination metadata
# ---------------------------------------------------------------------------


def update_destination_metadata(
    destination_id: str,
    state_dir: Path,
    **fields: Any,
) -> None:
    metadata_file = get_metadata_file_path(destination_id, state_dir)
    existing: Dict[str, Any] = {}
    if metadata_file.exists():
        try:
            with open(metadata_file, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(fields)
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"  ⚠ Warning: Could not update metadata: {exc}")


# ---------------------------------------------------------------------------
# Folder history
# ---------------------------------------------------------------------------


def append_folder_history(
    destination_id: str,
    state_dir: Path,
    folder_path: str,
    source_folder: Optional[str] = None,
    folder_id: Optional[str] = None,
    folder_title: Optional[str] = None,
    parent_id: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    state_file = get_state_file_path(destination_id, state_dir)
    key = f"{source_folder}/{folder_path}" if source_folder else folder_path
    entry = {
        "type": "folder",
        "folder_path": key,
        "folder_id": folder_id,
        "folder_title": folder_title,
        "parent_id": parent_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    try:
        with open(state_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"  ⚠ Warning: Could not append folder to state file: {exc}")


def get_folder_history(
    destination_id: str,
    state_dir: Path,
    folder_path: str,
    source_folder: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    state = load_sync_state(destination_id, state_dir)
    if source_folder:
        prefixed = f"{source_folder}/{folder_path}"
        if prefixed in state["folders"]:
            return state["folders"][prefixed]
    return state["folders"].get(folder_path)


def update_folder_history(
    destination_id: str,
    state_dir: Path,
    folder_path: str,
    source_folder: Optional[str] = None,
    folder_id: Optional[str] = None,
    folder_title: Optional[str] = None,
    parent_id: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    existing = get_folder_history(destination_id, state_dir, folder_path, source_folder) or {}
    append_folder_history(
        destination_id,
        state_dir,
        folder_path,
        source_folder=source_folder,
        folder_id=folder_id or existing.get("folder_id"),
        folder_title=folder_title or existing.get("folder_title"),
        parent_id=parent_id or existing.get("parent_id"),
        status=status,
    )


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def compute_content_hash(content: str) -> str:
    """SHA-256 hex digest for drift detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_content_signature(markdown_content: str) -> str:
    """
    Short identity signature from headings + first 500 chars.
    Used for rename detection.
    """
    lines = markdown_content.split("\n")
    headings = [line.strip() for line in lines if line.strip().startswith("#")]
    base = "\n".join(headings[:5]) + "\n" + markdown_content[:500]
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def find_by_signature(
    sync_state: Dict[str, Any],
    signature: str,
    exclude_path: str,
) -> Optional[Dict[str, Any]]:
    """Find an entry by content signature (rename detection)."""
    for path, entry in sync_state.get("sync_history", {}).items():
        if path != exclude_path and entry.get("content_signature") == signature:
            return {"old_path": path, **entry}
    return None


# ---------------------------------------------------------------------------
# State compaction
# ---------------------------------------------------------------------------


def compact_sync_state(
    destination_id: str,
    state_dir: Path,
) -> Tuple[int, int]:
    """
    Remove duplicate JSONL entries, keeping only the latest per path.

    Returns:
        (original_lines, compacted_lines)
    """
    state_file = get_state_file_path(destination_id, state_dir)
    if not state_file.exists():
        return 0, 0

    pages: Dict[str, Any] = {}
    folders: Dict[str, Any] = {}
    original_count = 0

    try:
        with open(state_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                original_count += 1
                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type", "page")
                    key = entry.get("file_path") or entry.get("folder_path")
                    if key:
                        if entry_type == "folder":
                            folders[key] = entry
                        else:
                            pages[key] = entry
                except json.JSONDecodeError:
                    continue

        compacted_count = len(pages) + len(folders)
        if compacted_count >= original_count:
            return original_count, compacted_count

        with open(state_file, "w", encoding="utf-8") as f:
            for entry in folders.values():
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            for entry in pages.values():
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return original_count, compacted_count
    except OSError as exc:
        print(f"  ⚠ Warning: Could not compact sync state: {exc}")
        return original_count, original_count
