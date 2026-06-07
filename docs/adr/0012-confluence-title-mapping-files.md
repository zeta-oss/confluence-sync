# ADR 0012: Confluence Title Mapping Files

## Status

Accepted

## Date

2026-01-27

## Context

Confluence Cloud requires unique titles for both pages and folders within a space. When syncing documentation from a Git repository, we encounter situations where:

1. Multiple folders have the same name (e.g., `examples/` appears under different parent directories)
2. Multiple pages might have the same title derived from their filename

The sync system cannot distinguish between:
- A remote folder that should be reused by the sync
- A remote folder with the same name that belongs to a different part of the hierarchy

Auto-generating unique titles (e.g., appending parent folder names) creates several problems:
- Titles become unpredictable and hard to reference
- Links between pages become fragile
- The mapping between local and remote content becomes opaque
- Future sync runs might generate different titles based on creation order

## Decision

We will support a `.confluence-mapping.yaml` file in each source folder that explicitly maps:

1. **Local subfolder names** → **Confluence folder titles**
2. **Local page filenames** → **Confluence page titles**

### Mapping File Format

```yaml
# .confluence-mapping.yaml
folders:
  examples: "Examples — Seer Sentinels"  # local-folder-name: confluence-title
  scratchpad: "Scratchpad — Security"

pages:
  README.md: "Seer Sentinels Overview"  # local-filename: confluence-title
  architecture.md: "Sentinel Architecture Design"
```

### Behavior

1. **If a mapping file exists**: Use the mapped title for folders/pages defined in it
2. **If no mapping file exists**: Use the current behavior (derive title from folder/file name)
3. **If a mapped title cannot be created** (e.g., still conflicts): Report as failure, do not auto-generate
4. **Local paths remain unchanged**: All internal dereferencing uses local paths, not Confluence titles

### Implementation Notes

- The mapping file is read during content preparation phase
- Title mappings are applied before content is sent to Confluence
- Link conversion uses the mapped titles when resolving cross-references
- The sync state continues to use local paths as keys

## Consequences

### Positive

- Explicit control over Confluence titles
- Predictable mapping between local and remote content
- Clear error messages when conflicts occur
- Maintainers can intentionally choose unique titles
- No surprising auto-generated title suffixes

### Negative

- Requires manual intervention when title conflicts occur
- Additional files to maintain in the repository
- Need to update mapping files when adding new content with conflicting names

### Guardrails

**IMPORTANT**: The sync system MUST NOT auto-generate unique folder or page titles. If a title conflict cannot be resolved via mapping file, the sync MUST fail with a clear error message directing the user to add a mapping entry.

This decision explicitly rejects approaches such as:
- Appending parent folder names to create unique titles
- Adding numeric suffixes to conflicting titles
- Using path-based hashes or identifiers
- Any form of automatic title disambiguation

The rationale is that predictable, human-readable titles are more important than automatic conflict resolution.

## References

- Confluence Cloud folder/page title uniqueness constraint
- Previous failed attempts at auto-disambiguation causing confusion
