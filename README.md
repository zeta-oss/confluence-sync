# confluence-sync

Sync Markdown documentation to Confluence — a standalone CLI tool installable via Homebrew.

## Install

```bash
brew tap zeta-oss/confluence-sync https://github.com/zeta-oss/confluence-sync.git
brew install confluence-sync
```

Or from source:

```bash
pip install -e .
```

## Quick start

```bash
cd ~/Git/my-docs-repo
confluence-sync init
# Edit .confluence-sync/confluence-sync.yml
confluence-sync doctor
confluence-sync sync -d my-destination
```

## Documentation

- [User Guide](docs/USER-GUIDE.md) — install, configure, sync, troubleshoot
- [Developer Guide](docs/DEVELOPER-GUIDE.md) — architecture, contributing, release
- [Migration Guide](docs/MIGRATION.md) — moving from `_confluence_sync`

## License

MIT. © zeta-oss contributors.
