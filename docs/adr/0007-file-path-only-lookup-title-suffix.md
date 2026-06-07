# ADR 0007: File Path-Only Lookup with Title Suffix Sequence

**NOTE**: This ADR is superseded by ADR 0010 (Remove Title Suffixing). Title suffixing has been removed. This ADR is retained for historical context.

## Status
Superseded (see ADR 0010)

## Context
The sync system needs to reliably map local Markdown files to Confluence pages. The previous approach used title-based search as a fallback when pages weren't in sync state, which led to several issues:

1. **Title ambiguity**: Page titles are not unique across a Confluence space, making title-based search unreliable
2. **Title conflicts**: When a page with the same title exists outside the destination root hierarchy, Confluence blocks creation even though it's unrelated
3. **Title changes**: If a page title is modified in Confluence (e.g., with a suffix to resolve conflicts), future lookups by original title fail
4. **Complexity**: Title search adds unnecessary complexity and API calls

## Decision
We will use **file path as the only lookup key** and implement a **title suffix sequence** for handling conflicts:

### Core Principles
1. **File path is the source of truth**: All lookups use `file_path` → `page_id` mapping from sync state
2. **No title-based search**: Title is only used for display in Confluence, not for lookup
3. **Suffix sequence for conflicts**: When creation fails with "already exists", automatically try titles with suffix `(1)`, `(2)`, etc.
4. **Store actual title used**: Sync state stores both `page_title_original` (from Markdown) and `page_title_actual` (what's actually in Confluence)

### Lookup Hierarchy
1. **Primary**: Check sync state by `file_path` → get `page_id` → use that page
2. **Fallback**: If not in sync state, create new page (with suffix sequence if needed)
3. **No title search**: Never search by title

### Title Conflict Resolution
When creating a page:
- Try original title from Markdown
- If "already exists" error, try `{title} (1)`, then `{title} (2)`, etc.
- Store the actual title that worked in sync state

When updating a page:
- Use `page_title_actual` from sync state for the update
- If local title changed, try new title first, then suffix sequence if it conflicts

## Consequences

### Positive
- **Reliable**: File path is unique and stable
- **Simple**: No complex title search logic
- **Fast**: Fewer API calls (no search operations)
- **Handles conflicts**: Automatic suffix sequence resolves duplicate title issues
- **Clear errors**: Conflicts are explicit, not hidden by search fallbacks

### Negative
- **Recovery**: If sync state is lost, we can't recover by searching (but we can rebuild by iterating pages under root)
- **Title changes**: Requires suffix sequence logic, but this is simpler than title search

### Migration
- Existing sync state entries will have `page_title` which becomes `page_title_actual`
- We'll add `page_title_original` for new entries
- Old entries without `page_title_original` will use `page_title` as both

## Implementation Notes
- Remove `find_page_by_title()` and `find_page_by_title_space_wide()` methods (or mark as deprecated)
- Update `find_or_create_page()` to use suffix sequence instead of title search
- Update sync state schema to include `page_title_original` and `page_title_actual`
- Update `_update_page()` to handle title changes with suffix sequence
