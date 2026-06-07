# 0005. JSONL Format for Sync State

## Status

Accepted

## Date

2025-01-22

## Context

The initial implementation used JSON format for sync state, storing all sync history in a single JSON file. This approach had several issues:

1. **Performance**: Loading entire state file for every lookup (O(N) for each file)
2. **Memory**: Entire state loaded into memory at once
3. **Inefficiency**: For large syncs (100s of files), reloading entire file repeatedly
4. **Not streamable**: Can't append updates without rewriting entire file

The user requested JSONL (JSON Lines) format to allow streaming updates rather than serializing the whole repo state for every file.

### Constraints

- Must support per-destination state
- Must be human-readable for debugging
- Must support efficient lookups
- Must handle migration from old JSON format

### Requirements

- Streaming updates (append-only)
- Efficient loading for lookups
- Per-file history tracking
- Backward compatible migration

## Decision

We will use JSONL (JSON Lines) format for sync state:

1. **Format**: One JSON object per line, each representing a file's sync history
2. **File naming**: `sync-state-{destination_id}.jsonl` in destination data directory
3. **Loading**: Load all lines into in-memory dictionary once at start
4. **Updates**: Append new lines (streaming, no full rewrite)
5. **Metadata**: Separate small JSON file for destination-level metadata

### Key Points

- JSONL allows streaming updates (append-only)
- Load once at start, use in-memory dictionary for lookups
- Each line is independent JSON object
- Separate metadata file for destination-level info
- Automatic migration from old JSON format

## Alternatives Considered

### Alternative 1: Keep JSON Format

Continue using single JSON file with all state.

**Pros:**
- Simple format
- Easy to read
- Already implemented

**Cons:**
- Must rewrite entire file for each update
- Slow for large syncs
- High memory usage

**Why rejected:** Doesn't support streaming updates and is inefficient for large syncs.

---

### Alternative 2: SQLite Database

Use SQLite database for state storage.

**Pros:**
- Efficient queries
- ACID transactions
- Standard format

**Cons:**
- Binary format (not human-readable)
- Requires SQLite dependency
- More complex
- Over-engineering for this use case

**Why rejected:** JSONL provides sufficient benefits without database complexity.

---

### Alternative 3: Separate JSON File Per File

Store state for each file in separate JSON file.

**Pros:**
- Very granular
- Easy to update individual files

**Cons:**
- Too many files
- Hard to manage
- Slow filesystem operations

**Why rejected:** Too many files would be difficult to manage.

---

### Alternative 4: YAML Format

Use YAML instead of JSON/JSONL.

**Pros:**
- Human-readable
- Supports comments

**Cons:**
- Slower parsing
- Less standard for streaming
- JSONL is simpler

**Why rejected:** JSONL is more standard for streaming and simpler to parse.

## Consequences

### Positive

- **Streaming updates**: Can append without rewriting entire file
- **Better performance**: Load once, use in-memory dictionary
- **Efficient for large syncs**: O(1) lookups after initial load
- **Human-readable**: Can still read and debug state files
- **Scalable**: Handles hundreds of files efficiently

### Negative

- **Migration required**: Must migrate from old JSON format
- **Loading overhead**: Must load all lines at start (but only once)
- **No random access**: Must read sequentially (but only at start)

### Neutral

- File format change requires migration logic
- Separate metadata file for destination-level info

## Implementation Notes

- `sync_state.py` provides `load_sync_state()` that reads JSONL into dictionary
- `append_page_history()` appends new line to JSONL file
- Migration function converts old JSON to JSONL format
- Metadata stored separately in `sync-metadata.json` (small, infrequent updates)
- State loaded once at start of sync, used throughout

## Related Decisions

- [ADR-0003: Data Directory Structure](./0003-data-directory-structure.md) — State files stored in destination subdirectories
- [ADR-0004: Content Hash-Based Change Detection](./0004-content-hash-change-detection.md) — Content hash stored in state

## References

- JSONL Format: https://jsonlines.org/
- Python JSON: https://docs.python.org/3/library/json.html
