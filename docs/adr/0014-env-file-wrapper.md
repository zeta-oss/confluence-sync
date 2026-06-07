# 14. Environment File Wrapper Script

**Status:** **Superseded by [ADR 0025](0025-cli-env-loading.md)** — env loading is now built into the CLI via `paths.load_dotenv()`  
**Date:** 2026-01-27  
**Context:** The sync script requires `CONFLUENCE_TOKEN` environment variable, which is stored in `.env` file. We needed a convenient way to load the `.env` file before running the sync.

## Decision

Create a wrapper script `run-sync-with-env.py` that:
1. Loads environment variables from `data/.env` file
2. Executes the sync script with those environment variables set

## Details

### Implementation
- Created `_confluence_sync/run-sync-with-env.py`
- Loads `.env` file from `data/.env` directory
- Parses key=value pairs (supports quoted values)
- Sets environment variables only if not already set
- Executes `sync-to-confluence.py` with loaded environment

### Usage
```bash
python3 run-sync-with-env.py --destination hub-proposal-temphub
```

## Consequences

### Positive
- **Convenience**: No need to manually export environment variables
- **Security**: Keeps tokens in `.env` file (should be in `.gitignore`)
- **Consistency**: Same environment loading approach as test scripts

### Negative
- Additional wrapper script to maintain
- Users need to remember to use the wrapper instead of direct script execution

## Notes

- The `.env` file is located at `_confluence_sync/data/.env`
- The wrapper uses simple parsing (not `python-dotenv` library) to avoid dependencies
- Environment variables are only set if not already present (respects existing env)
