# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-06-07

### Added
- Comprehensive E2E six-layer testing plan covering L1 to L6.
- Homebrew formula and automated installation / testing workflow.
- Pre-scan title resolution mapping to guarantee robust cross-page anchor links on clean syncs.
- Flexible fallback options for personal space and user-specific space sync runs.
- Detailed developer guides, user guides, and architecture records (ADR).

### Fixed
- Modernized Homebrew `run_brew_test` logic to automatically provision temporary test taps.
- Resolved Confluence API heading ID stripping issue by checking for exact heading text fallbacks.
- Corrected global regex search/replace in release scripts that corrupted resource urls.
- Fixed code style issues and brought Ruff static analysis compliance to 100% green.
