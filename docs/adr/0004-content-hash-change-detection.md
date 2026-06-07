# 0004. Content Hash-Based Change Detection

## Status

Accepted

## Date

2025-01-22

## Context

The initial implementation compared page content by fetching the current page from Confluence and doing a string comparison. This approach had several issues:

1. **Slow**: Required API call for every file, even if unchanged
2. **Inefficient**: Fetched full page content just to check if it changed
3. **Network overhead**: Unnecessary API calls for unchanged files
4. **Rate limiting risk**: Too many API calls could hit rate limits

The user requested that we use file-specific commit hashes and content hashes to quickly determine if a file needs to be synced, avoiding unnecessary API calls.

### Constraints

- Must handle files that were edited directly in Confluence (external changes)
- Must be accurate (no false positives or negatives)
- Must work with the two-phase sync architecture
- Must support force sync option

### Requirements

- Fast change detection without API calls when possible
- Use SHA-256 hash of content for comparison
- Store content hash in sync state
- Support force sync to bypass hash checks

## Decision

We will use content hash-based change detection:

1. **Compute content hash**: SHA-256 hash of Confluence Storage Format content
2. **Store in state**: Save content hash with each sync
3. **Compare hashes**: In Phase 1, compare new hash with stored hash
4. **Skip if unchanged**: If hash matches and not force sync, mark as skipped
5. **Verify on sync**: In Phase 2, still verify with Confluence (for external edits)

### Key Points

- Content hash computed from final Confluence Storage Format (not Markdown)
- Hash stored in sync state for each file
- Quick comparison in Phase 1 (no API calls)
- Still verify with Confluence in Phase 2 (handles external edits)
- Force sync option bypasses hash check

## Alternatives Considered

### Alternative 1: File Modification Time

Compare file modification times to detect changes.

**Pros:**
- Simple
- No hash computation needed

**Cons:**
- Not reliable (can be modified without content change)
- Doesn't handle Confluence-side edits
- Timezone issues

**Why rejected:** Not reliable enough for accurate change detection.

---

### Alternative 2: Git Commit Hash Only

Use only Git commit hash to detect changes.

**Pros:**
- Simple
- Already available from Git

**Cons:**
- Doesn't detect content changes within same commit
- Doesn't handle Confluence-side edits
- Multiple files can have same commit hash

**Why rejected:** Doesn't provide fine-grained change detection.

---

### Alternative 3: Full Content Comparison

Always fetch and compare full content from Confluence.

**Pros:**
- Most accurate
- Handles all edge cases

**Cons:**
- Slow (requires API call for every file)
- Network overhead
- Rate limiting risk

**Why rejected:** Too slow for large syncs.

---

### Alternative 4: ETag/Conditional Requests

Use HTTP ETags or conditional requests for change detection.

**Pros:**
- Standard HTTP approach
- Efficient

**Cons:**
- Confluence API may not support ETags well
- Still requires API call (though lightweight)
- Not investigated yet

**Why rejected:** Not yet investigated, but could be future optimization.

## Consequences

### Positive

- **Fast change detection**: Hash comparison is instant (no API calls)
- **Reduced API calls**: Skip unchanged files without API calls
- **Better performance**: Especially for large syncs with few changes
- **Accurate**: SHA-256 provides reliable change detection

### Negative

- **Hash computation overhead**: Must compute hash for every file
- **State storage**: Must store hash in sync state
- **External edits**: Still need to verify with Confluence (handled in Phase 2)

### Neutral

- Requires hash computation in content preparation phase
- State file includes content hash field

## Implementation Notes

- `compute_content_hash()` function in `sync_state.py` uses SHA-256
- Hash computed from final Confluence Storage Format content
- Stored in sync state as `content_hash` field
- Compared in Phase 1 during content preparation
- Still verified in Phase 2 for external edits
- Force sync paths bypass hash check

## Related Decisions

- [ADR-0001: Two-Phase Sync Architecture](./0001-two-phase-sync-architecture.md) — Hash comparison happens in Phase 1
- [ADR-0005: JSONL Format for Sync State](./0005-jsonl-format-sync-state.md) — Hash stored in state

## References

- SHA-256: https://en.wikipedia.org/wiki/SHA-2
- Python hashlib: https://docs.python.org/3/library/hashlib.html
