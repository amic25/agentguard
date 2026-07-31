# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Initial public project and community launch materials.
- `ScanResult.completed`: the scan-integrity invariant, true only when every enabled rule ran to
  completion over every in-scope file.
- `RepoConfig`, the untrusted configuration type, and `Config.tightened_by`, the monotone merge that
  is the only route from it into an effective configuration.
- `docs/RULE_IDS.md`: the rule identifier policy — never reuse a retired ID, never silently rename,
  alias on change — plus the permanent register of retired identifiers.
- `max_line_length` (default 4096): an engine-level bound on the input handed to line-oriented
  rules, so an ill-behaved pattern cannot be turned into a denial of service by a long line. Like
  `max_file_size_kb`, a scanned repository may only lower it.
- `truncated_lines` on `ScanResult` and in the JSON, Markdown, and terminal reports, so a bounded
  scan is never silently mistaken for a complete one.

### Changed

- **The distribution is named `agentguard`, not `agentguard-sast`.** Renamed before first
  publication, so no package under the old name has ever existed on PyPI — early git history
  referencing `agentguard-sast` describes a name that was never published, not one that was
  retired. The import package and the CLI entry point were already `agentguard` and are
  unchanged; only the name you `pip install` is affected, and only for anyone who built from
  source before this release.
- **Exit code semantics.** A scan that does not complete now exits `2` where some cases previously
  exited `0`. Automation that treated `0` as "clean" was previously being misled; it is now correct.
  Files skipped by declared policy (`max_file_size_kb`) remain non-failing.
- **Config schema.** `plugins`, `disabled_rules`, and `severity_overrides` are no longer accepted in
  a `.agentguard.yml` discovered in the repository under scan; they now require an explicit
  `--config`. Migration: pass `--config .agentguard.yml` to keep the previous behaviour for a
  repository you own, or move those keys to an operator-supplied file. `agentguard init` now emits
  the repository-safe subset.
- **Rules declare their context; the engine enforces it.** `RuleMetadata` gained
  `languages` (required), `ignore_regions`, `require_nodes`, and `fixture_policy`. Language
  gating, comment/docstring/annotation awareness, node-kind gating, and test-fixture
  handling were each being re-derived inside individual rules, differently and mostly
  wrongly. They now live in `Scanner._admit` and apply to every rule, including plugins.
  **Breaking for plugin authors:** `RuleMetadata` now raises unless `languages` is
  declared. Nothing has been released, so no migration path is owed; see `docs/PLUGINS.md`.
- Credential findings in test, fixture, example, and documentation paths are reported at
  `Medium` with `low` confidence rather than `Critical`, and carry `fixture_path` metadata.
  Live credentials do reach test fixtures, so they are not silenced — but they no longer
  block the default `--fail-on high` gate. Every other rule is suppressed on those paths.

### Fixed

- A rule that raised on every file, or a file that could not be decoded, previously produced exit
  code `0` — indistinguishable from a clean scan, so CI reported green with zero coverage. The exit
  code now honours the same invariant that SARIF `executionSuccessful` already reported. Exit `2`
  outranks the `--fail-on` threshold.
- `AG002` read any `.exec()` or `.eval()` method as the builtin, because call-name
  resolution returned the bare attribute when the receiver was not a plain name.
  `super().exec(*command)` was reported as critical arbitrary code execution.
- `AG002` reported `eval` and `exec` over expressions that are entirely literal, where
  there is no attacker-controlled input.
- `AG001` matched inside docstrings, comments, and type annotations, so
  `token: "contextvars.Token[Any]"` was reported as a committed credential.
- `AG005` ran against manifests, reporting Dependabot's `directory: "/"` as unrestricted
  filesystem access, and matched `path` as a substring, reporting the HTTP route
  `streamable_http_path="/"` as a broad filesystem root.
- `AG007` matched every JavaScript `function(`, reporting IIFEs in vendored analytics
  snippets as unvalidated agent tools.
- `AG008` matched definition sites, reporting `def delete_file(...)` as an unapproved
  high-impact action.
- Fixture classification only considered the path *below* the scan root, so
  `agentguard scan tests/` read an entire test suite as production code — disabling the
  fixture policy exactly where it matters most. The scan root's own name now counts.

### Removed

- **`AG009` (known vulnerable dependency).** It bundled three hand-maintained advisories and read
  only `requirements*.txt` and `package.json`, and it fired zero times across five real agent
  projects (4,750 files). A stale, near-empty advisory database invites false confidence; a real one
  is a data-operations commitment this project has not made. Use `pip-audit`, `osv-scanner`, or
  Dependabot, as `docs/SECURITY_MODEL.md` already recommended. **The `AG009` identifier is retired
  permanently and will never be reused** — see the new `docs/RULE_IDS.md`. Migration: remove `AG009`
  from `disabled_rules`, `severity_overrides`, and any `# agentguard: ignore [AG009]` comments; they
  are now inert.
- The `packaging` runtime dependency, which existed solely for `AG009`. AgentGuard's runtime
  dependencies are now `pyyaml`, `rich`, and `typer`.

### Security

- **AG004 was a denial-of-service vector.** Its pattern nested two unbounded `.*` spans, making it
  cubic in line length: a 28 KB single line took 34 seconds, and the file-size cap permits 1 MB.
  Since AgentGuard runs on untrusted input in CI, a repository could hang its own scan. The pattern
  now searches in two steps and takes 32 ms on the same input (~1,066x faster), and the new
  `max_line_length` bound caps the input to every regex rule, including ones not yet written.
  Detection is unchanged: verified identical acceptance and column on 1,039,776 lines across 3,777
  files of real agent code, plus a differential test kept in `tests/test_redos.py`.
- **Scanning an untrusted repository could execute arbitrary code from that repository.** A
  `.agentguard.yml` in the scan target could name modules under `plugins:`, which were passed
  directly to `importlib.import_module`. Scanning a hostile repository — the tool's primary
  advertised use case — imported attacker-controlled code, and the scan then reported clean and
  exited 0. Repository-provided configuration is now a separate type with no `plugins` field, and it
  can only tighten a scan. The same fix closes repository control over `follow_symlinks`,
  `max_file_size_kb`, and `exclude`.

## [0.1.0] - 2026-07-16 — NEVER PUBLISHED

> **This release does not exist.** The entry below was written in advance and the release
> was never cut: no `v0.1.0` tag was ever pushed, and nothing was published to PyPI. It is
> kept rather than deleted because a corrected record is better history than a clean one —
> and because anyone reading `[0.1.0]` elsewhere in this file needs to know it never
> shipped. The first published release will be `0.2.0`.

### Added

- Python and JavaScript/TypeScript project discovery with safe size, symlink, and exclusion controls.
- Ten built-in rules for secrets, command execution, tool permissions, prompt injection, filesystem access, external APIs, validation, approval gates, and dependencies.
- Terminal, JSON, Markdown, and SARIF 2.1.0 reporting.
- Configurable severity thresholds, rule suppression, severity overrides, and module/entry-point plugins.
- Docker image, typed Python package, tests, CI, CodeQL, dependency review, release workflow, and open-source governance files.
- `.mts`/`.cts` source discovery: these now map to the `typescript` language, so existing
  TypeScript-aware rules (AG002, AG004, AG006, AG007, etc.) run against them with no
  rule-level changes.

[Unreleased]: https://github.com/amic25/agentguard/commits/main
[0.1.0]: # (never published - no tag exists)
