# ADR 0010: Remove Title Suffixing

## Status
Accepted

## Context
The previous implementation automatically generated title suffixes (e.g., "Title (1)", "Title (2)") when page title conflicts occurred. This approach had problems:
1. Created duplicate pages with confusing titles
2. Made it difficult to identify the "correct" page
3. Polluted Confluence spaces with multiple versions
4. Made sync state management complex (tracking original vs. actual titles)

## Decision
Remove automatic title suffixing. Instead, raise clear errors when title conflicts occur.

### Changes Made
1. **Removed Suffix Logic**: Removed all code that generates title suffixes
2. **Single Attempt Creation**: Pages are created with original title in a single attempt
3. **Conflict Detection**: If "already exists" error occurs, search for existing page
4. **Clear Errors**: Raise `TitleConflictError` if conflict cannot be resolved

### Behavior
- **Page Creation**: Try once with original title. If conflict, search for existing page. If found, use it. If not found, raise error.
- **Page Update**: Try once with new title. If conflict, raise error (don't create duplicate).
- **Error Handling**: Clear error messages explain the conflict and suggest resolution.

## Consequences
### Positive
- No duplicate pages created
- Clear error messages for conflicts
- Simpler sync state (no title tracking complexity)
- Users can manually resolve conflicts

### Negative
- Requires manual intervention for title conflicts
- May fail sync if conflicts exist
- Users must resolve conflicts before sync can proceed

## Implementation
- Removed suffix loops from `find_or_create_page()`
- Removed suffix logic from `_update_page()`
- Added `TitleConflictError` exception class
- Updated error handling to provide clear conflict messages
- Updated tests to verify conflict handling
