"""Unit tests for sync_state.py — ported from test_content_signature.py."""

from __future__ import annotations

from confluence_sync.sync_state import (
    append_page_history,
    compute_content_hash,
    compute_content_signature,
    find_by_signature,
    get_state_file_path,
    load_sync_state,
)

# ---------------------------------------------------------------------------
# compute_content_signature
# ---------------------------------------------------------------------------


def test_signature_same_content_same_hash():
    c1 = "# Title\n\nSome content here."
    c2 = "# Title\n\nSome content here."
    assert compute_content_signature(c1) == compute_content_signature(c2)


def test_signature_different_content():
    c1 = "# Title\n\nSome content here."
    c2 = "# Different Title\n\nDifferent content."
    assert compute_content_signature(c1) != compute_content_signature(c2)


def test_signature_heading_structural_change():
    c1 = "# Title\n\nContent."
    c2 = "# Title\n## Subtitle\n\nContent."
    assert compute_content_signature(c1) != compute_content_signature(c2)


def test_signature_empty_returns_16_chars():
    sig = compute_content_signature("")
    assert sig is not None
    assert len(sig) == 16


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


def test_content_hash_deterministic():
    assert compute_content_hash("hello") == compute_content_hash("hello")


def test_content_hash_differs():
    assert compute_content_hash("hello") != compute_content_hash("world")


# ---------------------------------------------------------------------------
# append_page_history + load_sync_state round-trip
# ---------------------------------------------------------------------------


def test_jsonl_round_trip(tmp_path):
    state_dir = tmp_path / "state"
    dest_id = "my-dest"

    append_page_history(
        dest_id,
        state_dir,
        file_path="docs/index.md",
        page_id="12345",
        page_title="Index",
        sync_status="created",
        content_hash="abc123",
    )
    append_page_history(
        dest_id,
        state_dir,
        file_path="docs/guide.md",
        page_id="67890",
        page_title="Guide",
        sync_status="updated",
        content_hash="def456",
    )

    state = load_sync_state(dest_id, state_dir)
    assert "docs/index.md" in state["sync_history"]
    assert state["sync_history"]["docs/index.md"]["page_id"] == "12345"
    assert "docs/guide.md" in state["sync_history"]


def test_state_stored_under_dest_subdir(tmp_path):
    state_dir = tmp_path / "destinations"
    dest_id = "mytest"
    append_page_history(dest_id, state_dir, file_path="f.md")
    state_file = get_state_file_path(dest_id, state_dir)
    assert state_file.exists()
    # Must be under state_dir / dest_id /
    assert state_file.parent == state_dir / dest_id


# ---------------------------------------------------------------------------
# find_by_signature
# ---------------------------------------------------------------------------


def test_find_by_signature():
    sig = compute_content_signature("# Title\n\nContent.")
    sync_state = {
        "sync_history": {
            "old/file.md": {
                "page_id": "111",
                "content_signature": sig,
            }
        }
    }
    result = find_by_signature(sync_state, sig, exclude_path="new/file.md")
    assert result is not None
    assert result["old_path"] == "old/file.md"


def test_find_by_signature_excludes_self():
    sig = compute_content_signature("# Title\n\nContent.")
    sync_state = {
        "sync_history": {
            "same/file.md": {"page_id": "111", "content_signature": sig}
        }
    }
    result = find_by_signature(sync_state, sig, exclude_path="same/file.md")
    assert result is None
