# 0002. Module Separation: Content Preparer and Confluence Sync

## Status

Accepted

## Date

2025-01-22

## Context

The initial implementation had all functionality in a single large `ConfluenceSync` class that handled both content preparation (Markdown conversion, link resolution) and Confluence API interactions. This created several issues:

1. **Tight coupling**: Content preparation logic was mixed with API calls
2. **Hard to test**: Couldn't test content conversion without network access
3. **Unclear boundaries**: No clear separation between local operations and network operations
4. **Code complexity**: Single class handling too many responsibilities

The user requested that we split the code into two separate modules with clearly defined boundaries and individual tests.

### Constraints

- Must maintain backward compatibility with existing configuration
- Must preserve all existing functionality
- Modules should be independently testable

### Requirements

- Clear separation of concerns
- Content preparer must have no dependencies on Confluence API
- Confluence sync must operate on prepared content only
- Each module should have well-defined interfaces

## Decision

We will split the code into two separate modules:

1. **`content_preparer.py`**: Content Preparation Module
   - Handles all local file processing
   - Converts Markdown to Confluence Storage Format
   - Extracts Git metadata
   - Builds PreparedContent objects
   - No API calls to Confluence
   - Fully testable without network access

2. **`confluence_sync.py`**: Confluence Sync Module
   - Handles all Confluence REST API interactions
   - Operates on PreparedContent objects
   - Performs parallel syncing
   - Thread-safe operations
   - Clear input/output contracts

### Key Points

- Content preparer has zero dependencies on Confluence API
- Confluence sync only operates on PreparedContent objects
- Both modules can be tested independently
- Clear interfaces between modules
- Main script orchestrates both modules

## Alternatives Considered

### Alternative 1: Keep Single Module with Internal Separation

Keep everything in one file but organize into separate classes.

**Pros:**
- Simpler file structure
- All code in one place

**Cons:**
- Still hard to test independently
- No clear module boundaries
- Doesn't address testability concerns

**Why rejected:** Doesn't provide the clear boundaries and testability the user requested.

---

### Alternative 2: Three Modules (Preparer, Sync, Orchestrator)

Split into three modules: preparer, sync, and a main orchestrator.

**Pros:**
- Even clearer separation
- Orchestrator handles coordination

**Cons:**
- More complexity
- Over-engineering for current needs
- Main script already serves as orchestrator

**Why rejected:** Two modules provide sufficient separation without unnecessary complexity.

---

### Alternative 3: Plugin Architecture

Create a plugin system where preparers and syncers are pluggable.

**Pros:**
- Highly extensible
- Could support different content formats

**Cons:**
- Significant over-engineering
- Adds complexity without clear benefit
- YAGNI principle applies

**Why rejected:** Current requirements don't justify plugin architecture.

## Consequences

### Positive

- **Clear boundaries**: Each module has a single, well-defined responsibility
- **Testability**: Content preparer can be tested without network access
- **Maintainability**: Easier to understand and modify each module independently
- **Reusability**: Modules can be used independently if needed
- **Documentation**: Clear module-level documentation of responsibilities

### Negative

- **More files**: Code is split across multiple files
- **Coordination overhead**: Main script must coordinate between modules
- **Interface design**: Must carefully design interfaces between modules

### Neutral

- Requires refactoring existing code
- May require updating tests

## Implementation Notes

- `ContentPreparer` class in `content_preparer.py`
- `ConfluenceSync` class in `confluence_sync.py`
- `PreparedContent` dataclass shared between modules
- Main script (`sync-to-confluence.py`) orchestrates both modules
- Each module has clear docstrings explaining boundaries

## Related Decisions

- [ADR-0001: Two-Phase Sync Architecture](./0001-two-phase-sync-architecture.md) — This separation enables the two-phase approach
- [ADR-0003: Data Directory Structure](./0003-data-directory-structure.md) — Modules use shared data directory

## References

- Single Responsibility Principle: https://en.wikipedia.org/wiki/Single-responsibility_principle
- Python Module Best Practices: https://docs.python.org/3/tutorial/modules.html
