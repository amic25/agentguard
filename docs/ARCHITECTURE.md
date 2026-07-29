# Architecture

AgentGuard is a small, deterministic pipeline designed for safe local and CI execution.

1. The CLI validates arguments and builds the effective configuration. A config discovered inside the repository under scan is untrusted and may only tighten it; see [Security model](SECURITY_MODEL.md#configuration-trust-boundary).
2. Discovery walks only supported text files, excludes dependency/build directories, refuses symlinks by default, and caps file size.
3. `SourceFile` normalizes path, content, language, and length-bounded lines, and lazily derives a Python AST plus the file's comment, docstring, string, and annotation regions.
4. Built-in rules and plugin rules inspect one file at a time and emit immutable `Finding` objects.
5. The scanner applies each rule's declared context gates — language, ignored regions, required node kinds, fixture policy — then suppressions and severity overrides, then sorts deterministically.
6. Reporters serialize the same result to terminal, JSON, Markdown, or SARIF.
7. The exit code reflects whether every enabled rule ran to completion over every in-scope file, not merely whether findings were produced.

## Package boundaries

| Module | Responsibility |
|---|---|
| `config.py` | configuration schema and safe defaults |
| `context.py` | decoded source representation, lazy syntax trees, fixture-path classification |
| `regions.py` | comment, docstring, string, and annotation spans per language |
| `scanner.py` | file discovery, orchestration, suppression, error isolation |
| `rules/` | built-in rule implementations and public rule base class |
| `plugins.py` | entry-point and explicit-module discovery |
| `models.py` | stable finding, location, severity, and result models |
| `reporters.py` | human and machine report serialization |
| `cli.py` | command interface and exit-code contract |

## Design decisions

- **Never execute target code.** Imports are limited to plugins named in an operator-supplied config. A repository under scan cannot name one; the untrusted config type has no field for it.
- **Rules declare context; the engine enforces it.** Language gating, comment and docstring awareness, node-kind gating, and fixture handling are `RuleMetadata` fields applied centrally, not logic each rule reimplements. Nine rules each guessing separately produced a 92% false-positive rate at gating severity.
- **Bounded coverage is reported, never silent.** Skipped files and truncated lines appear in every report, because a bounded scan must not be mistaken for a complete one.
- **Offline by default.** Results do not change because a remote service is unavailable.
- **One normalized finding model.** Every output format contains the same core evidence and remediation.
- **Per-rule error isolation.** A plugin defect becomes a scan warning rather than hiding all other results.
- **Stable IDs.** CI suppressions and SARIF history remain meaningful across releases. Retired identifiers are never reissued; see [Rule identifier policy](RULE_IDS.md).
- **Detection quality is a measured number.** `make bench` scores every rule against a labeled corpus; no accuracy claim ships without it.
- **Conservative file access.** Symlinks are skipped and very large files are bounded unless the user opts in.

## Extending the system

External packages register one rule, a list of rules, or a factory under the `agentguard.rules` entry-point group. Local organizational rules may be named under `plugins` in configuration. See [PLUGINS.md](PLUGINS.md).
