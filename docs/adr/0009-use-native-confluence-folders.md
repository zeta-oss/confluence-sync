# ADR 0009: Use Native Confluence Folders

## Status
Accepted

## Context
The previous implementation used "directory pages" - regular Confluence pages with `'type': 'page'` that were used to represent directory structure. This approach had several problems:
1. Pages and folders competed for titles in the same namespace
2. Directory pages had content (README content or generated content), making them confusing
3. Hierarchy was maintained through parent-child page relationships, which was fragile
4. Title conflicts between directory pages and regular pages

Confluence REST API v2 provides native folder support (`/wiki/api/v2/folders`) which separates structure (folders) from content (pages).

## Decision
Replace directory pages with native Confluence folders using REST API v2.

### Changes Made
1. **Folder Creation**: Use `POST /wiki/api/v2/folders` to create folders
2. **Folder Tracking**: Track folders separately from pages in sync state
3. **Page Parents**: Pages use folder IDs as parents (not page IDs)
4. **README Handling**: README.md files remain as separate pages under folders (not folder content)

### Key Differences
- Folders are structure-only (no content)
- Folders have separate namespace from pages (no title conflicts)
- Pages are created under folders using `parentId` (folder ID)
- README files are regular pages, not folder content

## Consequences
### Positive
- Clear separation between structure (folders) and content (pages)
- No title conflicts between folders and pages
- More intuitive hierarchy representation
- Better alignment with Confluence's native model

### Negative
- Requires migration from old directory page format
- Folders cannot have content (README must be separate page)
- Some API limitations (e.g., folder updates may not be fully supported)

## Implementation
- Added `create_folder()`, `get_folder()`, `delete_folder()` methods
- Updated `content_preparer.py` to create folder entries instead of directory pages
- Updated sync flow to create folders before pages
- Updated sync state to track folders separately
- Created migration script to convert old directory pages to folders
