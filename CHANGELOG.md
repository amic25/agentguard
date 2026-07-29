# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Initial public project and community launch materials.
- `ScanResult.completed`: the scan-integrity invariant, true only when every enabled rule ran to
  completion over every in-scope file.

### Fixed

- A rule that raised on every file, or a file that could not be decoded, previously produced exit
  code `0` — indistinguishable from a clean scan, so CI reported green with zero coverage. The exit
  code now honours the same invariant that SARIF `executionSuccessful` already reported. Exit `2`
  outranks the `--fail-on` threshold.

### Changed

- **Exit code semantics.** A scan that does not complete now exits `2` where some cases previously
  exited `0`. Automation that treated `0` as "clean" was previously being misled; it is now correct.
  Files skipped by declared policy (`max_file_size_kb`) remain non-failing.

## [0.1.0] - 2026-07-16

### Added

- Python and JavaScript/TypeScript project discovery with safe size, symlink, and exclusion controls.
- Ten built-in rules for secrets, command execution, tool permissions, prompt injection, filesystem access, external APIs, validation, approval gates, and dependencies.
- Terminal, JSON, Markdown, and SARIF 2.1.0 reporting.
- Configurable severity thresholds, rule suppression, severity overrides, and module/entry-point plugins.
- Docker image, typed Python package, tests, CI, CodeQL, dependency review, release workflow, and open-source governance files.

[Unreleased]: https://github.com/amic25/agentguard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amic25/agentguard/releases/tag/v0.1.0
