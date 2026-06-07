# 0001. Two-Phase Sync Architecture

## Status

Accepted

## Date

2025-01-22

## Context

The initial implementation of the Confluence sync tool processed files sequentially, making API calls to Confluence for each file as it was processed. This approach had several performance issues:

1. **Slow for large syncs**: Processing hundreds of files sequentially meant long wait times
2. **Inefficient API usage**: Each file required multiple API calls (check existence, get version, update/create)
3. **No parallelization**: Network I/O was blocking, preventing concurrent operations
4. **Poor user experience**: No clear separation between fast local operations and slow network operations

The user requested a faster approach that would:
- Build all Confluence-formatted content locally first (super fast, no dependency on Confluence server)
- Then sync to Confluence in parallel threads using the already generated content
- Track sync status in state for content that is locally generated but not yet synced

### Constraints

- Must maintain backward compatibility with existing sync state format
- Must handle errors gracefully (one file failure shouldn't stop the entire sync)
- Must provide progress feedback to users
- Must support configurable parallel thread count (5-10 threads)

### Requirements

- Phase 1 must complete without any API calls to Confluence
- Phase 2 must support parallel execution with configurable thread count
- Content preparation must be deterministic and reproducible
- Sync status must be trackable in state

## Decision

We will implement a two-phase sync architecture:

1. **Phase 1: Content Preparation** (local, fast)
   - Read all Markdown files
   - Convert to Confluence Storage Format
   - Extract Git metadata
   - Build PreparedContent objects
   - Check sync state for change detection
   - No API calls to Confluence

2. **Phase 2: Parallel Sync** (network, parallel)
   - Use ThreadPoolExecutor with configurable thread count (default: 5)
   - Sync all PreparedContent objects in parallel
   - Update sync state as files are synced
   - Provide progress feedback

### Key Points

- Content preparation is completely isolated from Confluence API
- PreparedContent dataclass holds all information needed for syncing
- Parallel sync uses thread-safe operations
- Progress tracking shows both phases separately
- State updates happen incrementally during Phase 2

## Alternatives Considered

### Alternative 1: Sequential Processing with Batching

Process files in batches, making API calls as we go.

**Pros:**
- Simpler implementation
- Lower memory usage
- Can start syncing before all files are prepared

**Cons:**
- Still slower than parallel approach
- Complex error handling (partial batches)
- Harder to provide accurate progress

**Why rejected:** Doesn't address the core performance issue of sequential API calls.

---

### Alternative 2: Async/Await with asyncio

Use Python's asyncio for asynchronous API calls.

**Pros:**
- True async I/O
- Can handle more concurrent operations
- Modern Python pattern

**Cons:**
- Requires async HTTP library (aiohttp)
- More complex error handling
- ThreadPoolExecutor is simpler and sufficient

**Why rejected:** ThreadPoolExecutor provides sufficient parallelism for this use case and is simpler to implement and debug.

---

### Alternative 3: Single-Phase with Parallel Processing

Skip the preparation phase and process files in parallel directly.

**Pros:**
- Simpler architecture
- Lower memory footprint

**Cons:**
- Can't optimize content conversion (repeated work)
- Harder to provide accurate progress
- No clear separation of concerns

**Why rejected:** The preparation phase provides valuable benefits: clear progress tracking, ability to validate content before syncing, and better error handling.

## Consequences

### Positive

- **Significantly faster syncs**: Parallel API calls reduce total sync time
- **Better user experience**: Clear separation between fast local work and slow network work
- **Improved testability**: Content preparation can be tested without network access
- **Better error handling**: Can validate all content before attempting any syncs
- **Scalability**: Can handle hundreds of files efficiently

### Negative

- **Higher memory usage**: All PreparedContent objects held in memory
- **More complex code**: Two-phase architecture requires careful coordination
- **Potential thread safety issues**: Must ensure thread-safe state updates

### Neutral

- Requires refactoring existing code into separate modules
- Progress tracking must account for both phases

## Implementation Notes

- Created `content_preparer.py` module for Phase 1
- Created `confluence_sync.py` module for Phase 2
- `PreparedContent` dataclass holds all prepared content
- ThreadPoolExecutor with configurable `parallel_threads` (default: 5, max: 50)
- Progress callbacks provide real-time feedback
- State updates use thread-safe operations

## Related Decisions

- [ADR-0002: Module Separation](./0002-module-separation.md) — Separated content preparation from Confluence API calls
- [ADR-0004: Content Hash-Based Change Detection](./0004-content-hash-change-detection.md) — Enables efficient change detection in Phase 1

## References

- Python ThreadPoolExecutor: https://docs.python.org/3/library/concurrent.futures.html
- Confluence REST API: https://developer.atlassian.com/cloud/confluence/rest/
