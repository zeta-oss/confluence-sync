# ADR 0011: README Files as Separate Pages

## Status
Accepted

## Context
The previous implementation converted README.md content into directory page content, losing README as a separate page. With native folders, we need to decide how to handle README files:
1. Option A: README content becomes folder content (not possible - folders have no content)
2. Option B: README files are separate pages under folders
3. Option C: README files are ignored

## Decision
README.md files are created as separate pages under their respective folders.

### Rationale
- Folders cannot have content (structure only)
- README files are valuable documentation that should be accessible
- Keeping README as a page allows it to be linked, edited, and viewed independently
- Folder title can optionally be derived from README title, but README remains a page

### Implementation
1. **Folder Title**: Can optionally use README title for folder name (if README exists)
2. **README Processing**: README.md files are processed as regular pages in the file processing section
3. **Page Creation**: README pages are created under folders like any other page
4. **No Conversion**: README content is NOT converted to folder content

## Consequences
### Positive
- README files remain accessible as pages
- README can be linked and referenced
- Folder structure is clear (folders are structure-only)
- Consistent with how other Markdown files are handled

### Negative
- README appears as a page, not as folder "content"
- May be less intuitive for users expecting README to be folder content
- Folder and README page compete for visibility

## Implementation
- Removed code that converted README to directory page content
- README files are processed in the regular file processing loop
- Folder titles can optionally use README titles
- README pages are created under folders using `create_page_v2()`
