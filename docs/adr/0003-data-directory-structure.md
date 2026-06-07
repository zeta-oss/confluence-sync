# 0003. Data Directory Structure: One Subdirectory Per Destination

## Status

**Superseded by [ADR 0016](0016-project-local-config-directory.md)**

State is now stored at `{project-root}/.confluence-sync/destinations/{id}/` instead of the tool install directory.

## Date

2025-01-22

## Context

Initially, all sync state files, reports, and configuration were stored in the `_confluence_sync` directory alongside the script files. This created several issues:

1. **Cluttered directory**: Mix of code files and data files
2. **No organization**: All destinations' data mixed together
3. **Hard to manage**: Difficult to find files for a specific destination
4. **Configuration location**: Config file was in repo root, separate from data

The user requested:
- A `data` directory under which all data is maintained
- One subdirectory per destination for all sync state, reports, etc.
- Configuration file (`confluence-destinations.yaml`) under the `data` directory
- Script should take data directory path as input (default: `data` folder next to script)

### Constraints

- Must support migration from old file locations
- Must maintain backward compatibility during transition
- Must support multiple destinations per repository

### Requirements

- Clear separation of code and data
- Easy to find files for a specific destination
- Configurable data directory location
- Automatic migration from old locations

## Decision

We will organize all data under a `data` directory with the following structure:

```
_confluence_sync/
├── data/                          # Data directory (configurable)
│   ├── confluence-destinations.yaml  # Configuration file
│   ├── {destination_id}/         # One subdirectory per destination
│   │   ├── sync-state.jsonl     # Sync history (JSONL format)
│   │   ├── sync-metadata.json    # Destination metadata
│   │   └── sync-report-*.txt    # Sync reports
│   └── {another_destination_id}/
│       └── ...
├── content_preparer.py            # Code files
├── confluence_sync.py
└── ...
```

### Key Points

- `data/` directory contains all runtime data
- Each destination has its own subdirectory
- Configuration file is in `data/` directory
- Script accepts `--data-dir` parameter (defaults to `data/` next to script)
- Automatic migration from old file locations

## Alternatives Considered

### Alternative 1: Flat Structure in Data Directory

Store all files directly in `data/` with destination ID in filename.

**Pros:**
- Simpler structure
- Fewer directories

**Cons:**
- Harder to manage multiple destinations
- All files mixed together
- Difficult to clean up a destination

**Why rejected:** Subdirectories provide better organization and isolation.

---

### Alternative 2: Keep Old Structure with Data Directory

Move everything to `data/` but keep flat structure.

**Pros:**
- Minimal changes
- Easier migration

**Cons:**
- Still cluttered
- Doesn't solve organization problem
- Hard to manage multiple destinations

**Why rejected:** Doesn't address the core organizational issue.

---

### Alternative 3: Separate Data Directory Per Destination

Have completely separate data directories for each destination.

**Pros:**
- Maximum isolation
- Could be on different filesystems

**Cons:**
- Complex configuration
- Harder to manage
- Over-engineering

**Why rejected:** Single data directory with subdirectories provides sufficient isolation without complexity.

## Consequences

### Positive

- **Clear organization**: Easy to find files for a specific destination
- **Separation of concerns**: Code and data clearly separated
- **Easy cleanup**: Can delete a destination's subdirectory to remove all its data
- **Scalability**: Easy to add more destinations
- **Configurable location**: Can specify data directory location

### Negative

- **Migration required**: Must migrate existing state files
- **More directories**: Creates more directory structure
- **Path management**: Must manage paths to data directory

### Neutral

- Requires updating all file path references
- Configuration file location changes

## Implementation Notes

- `sync_state.py` provides `get_data_dir()` and `get_destination_data_dir()` functions
- All state/report functions accept optional `data_dir` parameter
- Main script accepts `--data-dir` argument
- Automatic migration from old file locations
- Configuration loader checks `data/` directory first, then old location

## Related Decisions

- [ADR-0005: JSONL Format for Sync State](./0005-jsonl-format-sync-state.md) — State files stored in destination subdirectories
- [ADR-0002: Module Separation](./0002-module-separation.md) — Modules use shared data directory structure

## References

- Python pathlib: https://docs.python.org/3/library/pathlib.html
- Data organization best practices
