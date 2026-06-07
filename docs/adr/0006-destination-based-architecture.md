# 0006. Destination-Based Configuration Architecture

## Status

Accepted

## Date

2025-01-22

## Context

The initial implementation supported syncing a single directory to a single Confluence space. This created limitations:

1. **Single destination**: Could only sync to one Confluence space/root page
2. **No flexibility**: Couldn't sync different folders to different destinations
3. **Mixed concerns**: Configuration mixed with code
4. **No isolation**: All syncs shared the same state

Users needed to:
- Sync multiple folders from the same repo to different Confluence spaces
- Combine multiple source folders into a single Confluence destination
- Have isolated state and reports per destination
- Configure destinations declaratively

### Constraints

- Must support multiple destinations per repository
- Must support multiple source folders per destination
- Must maintain backward compatibility
- Must be declarative (YAML configuration)

### Requirements

- YAML-based configuration
- Multiple destinations per config file
- Multiple source folders per destination
- Per-destination state isolation
- Per-destination reports

## Decision

We will implement a destination-based configuration architecture:

1. **Configuration file**: `confluence-destinations.yaml` in data directory
2. **Destination structure**: Each destination has:
   - Unique ID
   - Confluence target (URL, space, root page)
   - Source folders (one or more)
   - Credentials
   - Options (Git metadata, parallel threads, etc.)
3. **Per-destination state**: Each destination has isolated state and reports
4. **Multiple destinations**: One config file can define multiple destinations

### Key Points

- YAML configuration file defines all destinations
- Each destination has unique ID
- Source folders can be combined into single destination
- Per-destination state and reports
- Script can sync one destination or all destinations

## Alternatives Considered

### Alternative 1: Command-Line Arguments Only

Configure everything via command-line arguments.

**Pros:**
- Simple
- No config file needed

**Cons:**
- Hard to manage multiple destinations
- Repetitive command-line arguments
- No persistence

**Why rejected:** Doesn't scale to multiple destinations and is error-prone.

---

### Alternative 2: Environment Variables

Use environment variables for configuration.

**Pros:**
- Simple
- No files needed

**Cons:**
- Hard to manage multiple destinations
- Not declarative
- Easy to misconfigure

**Why rejected:** Doesn't provide the declarative, multi-destination approach needed.

---

### Alternative 3: Per-Destination Config Files

Have separate config file for each destination.

**Pros:**
- Clear separation
- Easy to manage individual destinations

**Cons:**
- Many files to manage
- Harder to see all destinations
- More complex

**Why rejected:** Single config file is easier to manage and provides better overview.

---

### Alternative 4: Database Configuration

Store configuration in database.

**Pros:**
- Dynamic configuration
- Can be updated via API

**Cons:**
- Over-engineering
- Requires database
- Not declarative

**Why rejected:** YAML file provides sufficient flexibility without database complexity.

## Consequences

### Positive

- **Flexibility**: Can sync same repo to multiple destinations
- **Organization**: Clear separation of destinations
- **Isolation**: Each destination has its own state
- **Declarative**: Easy to understand and modify
- **Scalability**: Easy to add more destinations

### Negative

- **Configuration complexity**: More complex than single destination
- **File management**: Must manage configuration file
- **Migration**: Must migrate from old single-destination approach

### Neutral

- Requires YAML parsing
- Configuration validation needed

## Implementation Notes

- `config_loader.py` handles YAML loading and validation
- Configuration schema validated on load
- Per-destination state in `data/{destination_id}/`
- Script supports `--destination` or `--all` flags
- Credentials resolved from environment variables

## Related Decisions

- [ADR-0003: Data Directory Structure](./0003-data-directory-structure.md) — Each destination has its own data subdirectory
- [ADR-0005: JSONL Format for Sync State](./0005-jsonl-format-sync-state.md) — Per-destination state files

## References

- YAML Specification: https://yaml.org/spec/
- Python PyYAML: https://pyyaml.org/
