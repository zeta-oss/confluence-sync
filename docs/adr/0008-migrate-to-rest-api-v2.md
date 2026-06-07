# ADR 0008: Migrate to Confluence REST API v2

## Status
Accepted

## Context
The current implementation uses Confluence REST API v1 (`/rest/api/content`, `/rest/api/space`) which is the older API version. Confluence has introduced REST API v2 (`/wiki/api/v2`) which provides:
- Better performance
- More consistent response formats
- Native folder support
- Improved error handling
- Better pagination support

## Decision
Migrate all Confluence API operations from REST API v1 to REST API v2.

### Changes Made
1. **Base API URL**: Changed from `/rest/api` to `/wiki/api/v2`
2. **Space Operations**: Use `/wiki/api/v2/spaces` instead of `/rest/api/space`
3. **Page Operations**: Use `/wiki/api/v2/pages` instead of `/rest/api/content`
4. **Folder Operations**: Use `/wiki/api/v2/folders` (new in v2)
5. **Space ID Resolution**: Added `_get_space_id()` method to resolve `space_id` from `space_key` using v2 API
6. **Response Parsing**: Updated all response parsing to handle v2 response structure

### Key Differences
- v2 uses `spaceId` (numeric ID) instead of `spaceKey` (string) for many operations
- v2 response structure is more consistent
- v2 uses cursor-based pagination instead of offset-based
- v2 has native folder support (not available in v1)

## Consequences
### Positive
- Access to native folder support
- Better API performance
- More consistent error handling
- Future-proof (v1 may be deprecated)

### Negative
- Requires space_id resolution (additional API call)
- Some v1 endpoints may not have direct v2 equivalents
- Response structure changes require code updates

## Implementation
- Updated `ConfluenceSync.__init__` to use v2 base URL
- Added `_get_space_id()` method for space ID resolution
- Updated all page operations to use `/wiki/api/v2/pages`
- Updated all folder operations to use `/wiki/api/v2/folders`
- Updated space operations to use `/wiki/api/v2/spaces`
- Added pagination helper `_paginate_v2()` for cursor-based pagination
