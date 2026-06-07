# 13. Parallel Folder Sync and Sync State Trust

**Status:** Accepted  
**Date:** 2026-01-27  
**Context:** Folder creation was sequential and slow, taking ~1.3 seconds per folder. Additionally, the sync was making unnecessary API calls to verify folders that hadn't changed.

## Decision

We will:
1. **Parallelize folder creation** by processing folders in batches grouped by depth level
2. **Trust sync state** for folders unless there's a conflict - skip API calls for unchanged folders

## Details

### Parallelization Strategy
- Folders are sorted by depth (shallow to deep) to ensure parents are created before children
- Folders are grouped by depth level
- Within each depth level, folders are processed in parallel using `ThreadPoolExecutor`
- Maximum parallel threads for folders: `min(parallel_threads, 8)` to avoid API rate limits
- Parent-child ordering is guaranteed: when processing depth N, all folders at depth N-1 are already in `folder_id_map`

### Sync State Trust
- If a folder exists in sync state with `folder_id`, `folder_title`, and `parent_id`
- And metadata (title, parent) hasn't changed
- Then trust the sync state and use the `folder_id` directly without making an API call
- Only make API calls when:
  - Folder not in sync state
  - Metadata has changed (title or parent)
  - A conflict is detected during creation

## Implementation

- Modified `sync-to-confluence.py` Phase 2a to:
  - Group folders by depth using `defaultdict`
  - Process folders depth-by-depth sequentially
  - Parallelize within each depth level
  - Trust sync state for unchanged folders

## Consequences

### Positive
- **Performance**: Folder creation is now much faster (parallel processing)
- **Efficiency**: Eliminates unnecessary API calls for unchanged folders
- **Correctness**: Parent-child ordering is maintained
- **Scalability**: Can handle large folder hierarchies efficiently

### Negative
- Slightly more complex code (depth-based grouping and parallel processing)
- Need to ensure thread-safety when reading/writing `folder_id_map`

## Notes

- Folder parallelization respects parent-child dependencies by processing depth-by-depth
- Sync state trust significantly reduces API calls for incremental syncs
- This optimization complements the existing page parallelization (12 threads)
