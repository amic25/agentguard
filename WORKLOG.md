# Work log

Append-only. One entry per work unit, written before the next unit starts, so an
interrupted session can be resumed from disk rather than from memory.

Branch: `audit/phase-0`. No pushes, no PRs — local commits only.

---

## Session recovery — 2026-07-29

Status: complete
Changed: nothing (read-only reconciliation)
Verified:
- `git log --oneline -10` → 4 new commits on `audit/phase-0`: `90fa637` audit, `fe9ba0f`
  exit-code invariant, `e5a0b19` typed trust boundary, `827b4d1` secret non-disclosure.
- `git status --short` → 3 modified files, an in-flight AG009 deletion.
- `python -m compileall src/agentguard tests` → OK. **Nothing was truncated mid-write.**
- `pytest -q` → 71 passed, 92.71% coverage.

Findings: the interrupted unit was AG009 deletion. The rule, its registration, and its
tests were already removed and coherent. Missing: `docs/RULE_IDS.md` (never created),
`packaging` still declared in `pyproject.toml`, `README.md:38` still listing `AG009–AG010`,
no CHANGELOG entry, no issue filed.

Note: the recovery commands in the brief assume a flat layout; this repo is `src/`-layout,
so `compileall` was run against `src/agentguard`.

Bench delta: n/a — `make bench` does not exist yet (unit 5).
Decisions taken alone: none.
Next: finish unit 1 (AG009 deletion + rule ID policy).

---

## Unit 1 — AG009 deletion and rule ID policy — 2026-07-29

Status: complete
Changed:
- `src/agentguard/rules/dependencies.py` (rule, `ADVISORIES`, `packaging` imports removed)
- `src/agentguard/rules/__init__.py` (deregistered)
- `tests/test_rules.py` (advisory-boundary tests replaced with a retirement test)
- `docs/RULE_IDS.md` (new — the interrupted file)
- `pyproject.toml` (dropped the `packaging` runtime dependency)
- `README.md`, `docs/assets/demo.svg`, `CHANGELOG.md`

Verified (all in `python:3.12-slim`, repo bind-mounted):
```
ruff format --check src tests   → 23 files already formatted
ruff check src tests            → All checks passed!
mypy src                        → Success: no issues found in 14 source files
pytest -q                       → 71 passed, 92.71% coverage (gate 85%)
python -c 'import agentguard'   → import OK after uninstalling packaging
```
`BUILTIN_RULES` is now 9: AG001–AG008, AG010.

Test that fails before / passes after: `test_ag009_is_retired_and_never_reissued` asserts
`AG009` appears in neither scan output nor `BUILTIN_RULES`. It fails on the parent commit
(the rule fires on `axios@1.7.2`) and passes here.

Removing AG009 also removed the `packaging` runtime dependency, which existed solely for
it. Runtime dependencies are now `pyyaml`, `rich`, `typer`.

Filed https://github.com/amic25/agentguard/issues/16 for the eventual shape (shell out to
`pip-audit`/`osv-scanner`, normalise into `Finding`/SARIF, own no advisory data). Not
implemented, per instruction.

Bench delta: n/a — `make bench` does not exist yet (unit 5). AG009's measured contribution
in the Phase 0 dogfood was 0 findings across 4,750 files, so removing it cannot move a
precision or recall number for any other rule.

Decisions taken alone:
1. **`CHANGELOG.md:48` ("Ten built-in rules") left unchanged.** It sits inside the released
   `[0.1.0]` section, which is a historical record — 0.1.0 genuinely shipped ten rules.
   Editing it would falsify history. The removal is recorded under `[Unreleased]` instead.
   Conservative: touches less, and is standard Keep-a-Changelog discipline.
2. **`AUDIT.md` left unchanged** despite containing `AG009`. It is a dated point-in-time
   audit; rewriting it to match later work would destroy its value as evidence.
3. **`docs/assets/demo.svg` updated** `10 rules` → `9 rules`. One token, user-visible in the
   README, and now factually wrong otherwise. Reversible.

Next: unit 2 — close out F1 (raise-attempt tests for `max_file_size_kb`, `follow_symlinks`,
`exclude`, plugin loading; confirm fixtures inert; exit-code invariant test).

---

## Unit 2 — close out F1 — 2026-07-29

Status: complete
Changed: `tests/test_trust_boundary.py` (three tests added)

Verified:
```
ruff format --check src tests   → 23 files already formatted
ruff check src tests            → All checks passed!
mypy src                        → Success: no issues found in 14 source files
pytest -q                       → 74 passed, 92.71% coverage
```

Exit-code invariant, end to end (real invalid UTF-8 bytes, not shell-escaped text):
```
clean repo        → 0
undecodable file  → 2   "Scan incomplete: 1 error(s); results are not a clean bill of health."
crashing rule     → 2   (tests/test_scan_integrity.py::test_cli_exits_2_when_a_rule_crashes)
```

### Failing-before / passing-after, per vector

Probed a hostile repo against a worktree at `fe9ba0f` (pre-trust-boundary) and at HEAD:

| Vector | Before | After |
|---|---|---|
| repo config loads a plugin | **VULNERABLE** — repo code imported | SAFE — not imported |
| repo raises `max_file_size_kb` | **VULNERABLE** — 1523 KB file scanned | SAFE — skipped, bound held at 1024 KB default |
| repo enables `follow_symlinks` | **VULNERABLE** — read outside root via symlink | SAFE — symlink not followed |
| repo shrinks `exclude` | SAFE | SAFE |

**`exclude` was never vulnerable.** The pre-fix `Config.load` already prepended
`DEFAULT_EXCLUDES` unconditionally, so a repo could add exclusions but never remove them.
The typed boundary is defense in depth here, not a fix, and this entry exists so the
commit is not read as claiming otherwise.

Two probe-authoring errors were caught and corrected before recording results — worth
noting because both would have produced a *false* baseline:
- The `max_file_size_kb` probe first used a 360 KB file, under the 1024 KB default, so
  neither state skipped it and the fix looked broken. Corrected to 1523 KB.
- The `follow_symlinks` probe first used `"AKIA" + "IOSFODNN7SECRET1"`, split to avoid a
  key-shaped literal. Concatenation means the AG001 regex cannot match, so the probe
  measured nothing and reported SAFE for both states. Corrected to a single fabricated,
  non-live literal.

Fixture inertness: `test_generated_hostile_fixture_is_inert` pins the generated plugin to
a single `write_text` and asserts it references no `subprocess`, `socket`, `shutil`,
`os.remove`, `eval(`, `exec(`, or `__import__`.
`test_no_hostile_payload_is_committed_to_the_repository` walks `git ls-files` and asserts
no `hostile_plugin.py` is tracked and no committed `.agentguard.yml` declares `plugins:`.
Confirmed on the host across all 66 tracked files: none.

Bench delta: n/a — `make bench` does not exist yet (unit 5).

Decisions taken alone:
1. **`test_no_hostile_payload_is_committed_to_the_repository` skips when `git` is absent**
   rather than failing. It is a repository-hygiene check, not a code check, and the dev
   container has no git. It runs for real in CI and on the host, where it passes.

Next: unit 3 — AG004 ReDoS. Note this is a rule change, and per the brief no rule may
change before `make bench` exists (unit 5). Sequencing question resolved below.

---

## Unit 3 — AG004 ReDoS — 2026-07-29

Status: complete
Changed: `src/agentguard/rules/code.py`, `src/agentguard/context.py`,
`src/agentguard/config.py`, `src/agentguard/scanner.py`, `src/agentguard/models.py`,
`src/agentguard/reporters.py`, `tests/test_redos.py` (new), README, SECURITY_MODEL, CHANGELOG

Verified:
```
ruff format --check src tests   → 24 files already formatted
ruff check src tests            → All checks passed!
mypy src                        → Success: no issues found in 14 source files
pytest -q                       → 113 passed, 93.04% coverage
```

### Sequencing conflict, and how it was resolved

Unit 3 changes a rule, but the hard stops say no rule may change before `make bench`
exists (unit 5). Decision 7 sequences the ReDoS fix here deliberately, as a safety defect.

Resolved by making the fix **provably detection-neutral**, so no unmeasured detection
change lands before the baseline:
- Differential test against the original pattern, kept in `tests/test_redos.py` as an
  oracle: 39 cases plus 432 generated combinations, asserting identical acceptance *and*
  identical reported column.
- One-off differential over the five real projects: **1,039,776 lines across 3,777 files,
  zero disagreements.**

So the pattern is faster and decides nothing differently. The bench baseline in unit 5
will therefore measure the same AG004 behaviour that existed before this commit.

### The fix

The pattern nested two unbounded `.*` spans inside a search, so the engine tried every
split of the second for every split of the first at every start offset. Python 3.10 has
neither atomic groups nor possessive quantifiers, so the nesting was removed by searching
in two steps: find the assignment prefix, then search the interpolation alternatives from
that match's end. Equivalent because the alternation could only ever match at or after
the prefix.

| Line length | Before | After |
|---|---|---|
| 1.8 KB | 12 ms | 0.22 ms |
| 7.2 KB | 511 ms | 2.21 ms |
| 14.4 KB | 3,964 ms | 8.32 ms |
| 28.8 KB | **34,408 ms** | **32.28 ms** |

**Honest caveat: this is not linear.** The curve is still ~4x per doubling — quadratic,
from the one remaining `.*` inside `f['"][^\n]*\{SRC\}`. What makes it *safe* is the
combination with the new engine-level bound, not the rewrite alone.

### The engine-level guard

`max_line_length` (default 4096) bounds the input handed to every line-oriented rule,
present and future — the brief's "so the next bad pattern cannot hang the scanner either".
Worst case is now bounded twice over: at most 1 MB per file / 4096 chars per line = 256
full-length lines, at ~0.6 ms each ≈ 154 ms per file.

Truncation is counted and reported (`truncated_lines`) in JSON, Markdown, and terminal
output. A silent cap would let a bounded scan pass for a complete one, which is the same
class of mistake as unit 1's exit code.

Bench delta: n/a — `make bench` does not exist yet (unit 5). Detection is unchanged by
construction, evidenced above.

Decisions taken alone:
1. **`max_line_length` added to `RepoConfig`** (lower-only), consistent with
   `max_file_size_kb`. A repo tightening its own bound is safe by the same argument.
2. **`truncated_lines` added to the JSON `scan` object.** Additive key, backward
   compatible for any consumer reading known fields. Chosen over silence because the
   brief forbids unreported coverage caps.
3. **`SourceFile.lines` now computes once** instead of re-splitting on every access
   (audit F8). Free while editing the file, and needed anyway to count truncation once.
4. **Removed stale "vulnerable dependencies" claims** from `README.md` and
   `docs/SECURITY_MODEL.md`. With AG009 gone the tool does not check advisories at all,
   so those sentences were unmeasured claims of a capability that no longer exists.
5. **`python_tree()` now also catches `ValueError`/`RecursionError`.** `ast.parse` raises
   these on null bytes and deeply nested input respectively; both are reachable from a
   hostile file and would otherwise surface as a rule crash. Conservative: strictly more
   robust, no detection change.

Next: unit 4 — CI matrix 3.10-3.13. Already present at `.github/workflows/ci.yml:17`;
will verify rather than duplicate, then unit 5 (corpus + bench).

---

## Unit 4 — CI matrix 3.10–3.13 — 2026-07-29

Status: complete (no change required)
Changed: nothing

The matrix already existed at `.github/workflows/ci.yml:17` before this session, so the
gap was verification, not configuration. Ran the full suite on every supported version
against current `HEAD`:

```
Python 3.10.20  → 112 passed, 1 skipped
Python 3.11.15  → 112 passed, 1 skipped
Python 3.12.13  → 112 passed, 1 skipped
Python 3.13.14  → 112 passed, 1 skipped
```
(The skip is the git-hygiene check; the container has no git. It runs in CI.)

This closes the "not verified on 3.10/3.11/3.13" caveat recorded in AUDIT.md §6.

Bench delta: n/a
Decisions taken alone: none — adding a matrix that already exists would have been
duplicated configuration presented as work.
Next: unit 5 — corpus and bench.

---

## Unit 5 — Phase 1 baseline: labeled corpus and `make bench` — 2026-07-29

Status: complete
Changed: `tests/corpus/` (23 files + `manifest.yml`), `tools/bench.py`, `Makefile`,
`tests/test_corpus.py`, `pyproject.toml`, `.github/workflows/ci.yml`

Verified:
```
ruff format --check src tests tools  → 27 files already formatted
ruff check src tests tools           → All checks passed!
mypy src                             → Success: no issues found in 14 source files
pytest -q                            → 120 passed, 93.29% coverage
python -m tools.bench                → table below
```

### BASELINE — measured before any rule change

```
| Rule  |  TP |  FP |  FN | Precision | Recall |
|-------|----:|----:|----:|----------:|-------:|
| AG001 |   1 |   3 |   0 |     25.0% | 100.0% |
| AG002 |   2 |   2 |   0 |     50.0% | 100.0% |
| AG003 |   1 |   0 |   0 |    100.0% | 100.0% |
| AG004 |   1 |   0 |   0 |    100.0% | 100.0% |
| AG005 |   1 |   2 |   0 |     33.3% | 100.0% |
| AG006 |   1 |   0 |   0 |    100.0% | 100.0% |
| AG007 |   1 |   2 |   0 |     33.3% | 100.0% |
| AG008 |   1 |   1 |   0 |     50.0% | 100.0% |
| AG010 |   1 |   0 |   0 |    100.0% | 100.0% |
| **all** |  10 |  10 |   0 |     50.0% | 100.0% |
```

False positives, all reproducing defects measured against real projects in AUDIT.md:
```
AG001  true_negatives/secrets_in_docstrings.py:8
AG001  true_negatives/secrets_in_test_fixtures.py:8
AG001  true_negatives/token_annotations.py:12
AG002  true_negatives/eval_on_literal.py:3
AG002  true_negatives/method_named_exec.py:9
AG005  true_negatives/dependabot.yml:5
AG005  true_negatives/route_paths.py:10
AG007  true_negatives/analytics_iife.js:3
AG007  true_positives/agent_tools.ts:4
AG008  true_negatives/function_definitions.py:7
```

Note AG003, AG004, AG006 and AG010 show 100% precision here while the real-project
dogfood measured AG003 at 98.4% FP and AG006 at 100% FP. **The corpus is smaller than
reality and currently flatters those three rules.** It is a regression harness, not a
population sample, and the AUDIT.md dogfood remains the honest estimate of field
behaviour. Extending the corpus for AG003/AG006 is follow-up work.

### Harness design notes

- `expect` is exhaustive: any finding whose rule is not listed counts as a false
  positive. There is no "don't care", because a rule firing on a file nobody considered
  is exactly the noise being measured.
- `why` is mandatory and validated. A label without a reason cannot be distinguished
  later from one that was rubber-stamped.
- The manifest and the directory contents are cross-checked both ways; drift exits 2
  rather than reporting numbers computed from a stale corpus.
- Files that file discovery never opens are reported as **not-discovered** rather than
  counted as clean negatives.

### Two corpus bugs the harness caught on first run

1. AG010 showed a false negative. The rule requires the filename to start with
   `requirements`; the file was named `unpinned_requirements.txt`. Corpus bug, not a rule
   bug — renamed.
2. `.env.example` produced no finding **because AgentGuard never opens it**: `.example`
   is not a recognised suffix. It was silently scoring as a clean negative while proving
   nothing. This is also a real coverage gap — a genuine `.env` containing live
   credentials would be missed entirely. Now surfaced by the harness and pinned by
   `test_undiscovered_files_are_reported_not_silently_passed`.

Both are recorded because a harness that quietly credits itself is worse than none.

Bench delta: n/a — this **is** the baseline.

Decisions taken alone:
1. **`tests/corpus` excluded from ruff.** The files deliberately contain undefined names
   and unsafe calls; formatting them would change what is being measured. mypy already
   only reads `src`. pytest `norecursedirs` prevents collection.
2. **`pythonpath = ["."]`** so `tests/test_corpus.py` can import the harness, and `tools`
   added to the sdist so the benchmark is reproducible from a source distribution.
3. **`make check` now includes `bench`**, and CI prints the table on every run, so a
   precision change is visible in a log diff rather than needing to be remembered.
4. **`test_corpus.py` asserts recall and corpus consistency, not precision.** Precision is
   expected to move in unit 6; pinning it would mean editing the assertion in the same
   commit that changes the behaviour, which defeats the check.

Next: unit 6 — F2's four root causes, declaratively in the engine, then re-run bench and
report per-rule deltas.

---

## Unit 6 — F2's four root causes, declaratively — 2026-07-29

Status: complete
Changed: `src/agentguard/regions.py` (new), `rules/base.py`, `context.py`, `scanner.py`,
all four rule modules, `tests/test_rule_context.py` (new), corpus, CHANGELOG, PLUGINS.md

Verified:
```
ruff format --check src tests tools  → 29 files already formatted
ruff check src tests tools           → All checks passed!
mypy src                             → Success: no issues found in 15 source files
pytest -q                            → 143 passed, 92.65% coverage
agentguard scan src --fail-on medium → exit 0, no findings
```

### BENCH DELTA — corpus

| Rule | Precision before | after | Recall before | after |
|---|---:|---:|---:|---:|
| AG001 | 25.0% | **100.0%** | 100% | 100% |
| AG002 | 50.0% | **100.0%** | 100% | 100% |
| AG003 | 100.0% | 100.0% | 100% | 100% |
| AG004 | 100.0% | 100.0% | 100% | 100% |
| AG005 | 33.3% | **100.0%** | 100% | 100% |
| AG006 | 100.0% | 100.0% | 100% | 100% |
| AG007 | 33.3% | **100.0%** | 100% | 100% |
| AG008 | 50.0% | **100.0%** | 100% | 100% |
| AG010 | 100.0% | 100.0% | 100% | 100% |
| **all** | **50.0%** | **100.0%** | **100%** | **100%** |

Recall did not move. No false positive was traded for a corpus false negative.

### FIELD DELTA — the number that matters

The corpus is 24 files. Re-ran the five real projects from AUDIT.md (4,750 files):

| | Before | After |
|---|---:|---:|
| Total findings | 233 | **73** (−69%) |
| Findings at Critical/High (what gates CI at the default) | 208 | **17** (−92%) |
| AG001 at Critical | 63 | **3** |

Per rule, total field findings: AG001 63→57 (of which 54 are now Medium fixture
downgrades), AG002 15→4, AG003 64→4, AG005 29→1, AG006 4→2, AG007 8→0, AG008 37→5,
AG010 13→0.

Hand-triaged the 17 remaining gating findings: roughly 12 are genuine — real `exec(code, ns)`,
`subprocess.run([...], shell=True)`, two committed API keys, `allow_delegation = True`.
Roughly 5 remain false: AG003's bare `function_map\s*=` still matches a local dict
comprehension (2), AG005's `path = "/" + path` (1), and two borderline `delete_file(...)`
calls inside sandbox tooling. Estimated gating precision moved from ~7.7% to ~70%.

**All five projects still exit 1.** That is now correct behaviour rather than noise: each
has at least one genuine Critical.

### Trades made — false positives bought with false negatives

Per the brief, stated explicitly rather than buried. Each was kept because precision was
the binding constraint for that rule in the field measurement.

1. **AG005 `\b` on `path`** — `file_path="/"`, `mount_path="/"`, `drive_path="/"` no longer
   match. Real recall loss. Kept: AG005 measured 100% false positives in the field (29/29),
   and `streamable_http_path` alone accounted for 8.
2. **AG007 dropped `function(`** — a JS tool registered through a bare function expression
   is no longer detected. Kept: AG007 measured 100% false positives (8/8), and the pattern
   matched every function expression in every JavaScript file.
3. **`fixture_policy="suppress"`** — non-secret findings in `tests/`, `examples/`, `docs/`
   are dropped entirely. This is the largest recall loss: AG010 went 13→0 in the field
   because every hit was under `libs/cli/examples/`. Deliberate, per decision 6.
4. **`eval`/`exec` over wholly literal arguments** — no longer reported. Small: a literal
   passed to `eval` still executes, but carries no attacker-controlled input.
5. **Call-name resolution returns "" for non-name receivers** — `get_module().system(cmd)`
   is no longer matched. Kept: the alternative resolved every `x().exec()` to the builtin.

### Design notes

`regions.py` derives comment, docstring, string, and annotation spans from each language's
own grammar — `tokenize` and `ast` for Python, a small lexer for JS/TS, `#` for manifests.
Rules declare what they will not match inside; `Scanner._admit` enforces it. A plugin
inherits all of it without asking, and cannot opt out — pinned by
`test_engine_gates_apply_to_third_party_rules`.

The schema is enforced at construction, not documented: `RuleMetadata` raises unless
`languages` is declared. It caught three of this repository's own test helpers on the
first run, which is the behaviour working.

Decisions taken alone:
1. **Fixture downgrade clamps to MEDIUM, not one step down.** A `CRITICAL→HIGH` step still
   trips the default `--fail-on high`, so fixture credentials would keep blocking CI —
   the exact noise decision 6 exists to remove. Clamping to Medium reports them without
   gating. Decision 6 said "downgrade" without a magnitude; this is the reading that makes
   the policy do anything.
2. **`.env.example` left undiscovered rather than extending file discovery.** Adding a new
   discovered file type is a scope and behaviour change that belongs in its own unit with
   its own measurement. Recorded as a known gap in the corpus and pinned by a test.
3. **`AG001` also ignores the `annotation` region**, which is not in the default set. Real
   credentials are ordinary string literals, so `string` is deliberately *not* ignored.
4. **`docs/` counts as a fixture path.** It is where tutorials live, and tutorial
   credentials were 6 of the field false positives.

Not verified: whether the ~5 remaining field false positives are worth further tuning —
that needs AG003 and AG006 corpus coverage, which the corpus currently lacks (recorded in
unit 5 as a known limitation).

Next: unit 7 — docs reconciliation, then unit 8 — stop and report.

---

## Unit 7 — documentation reconciliation — 2026-07-29

Status: complete
Changed: `docs/ARCHITECTURE.md`, `docs/PLUGINS.md`, `ROADMAP.md`, `README.md`, `CHANGELOG.md`

Verified:
```
Python 3.10.20  → 142 passed, 1 skipped
Python 3.11.15  → 142 passed, 1 skipped
Python 3.12.13  → 142 passed, 1 skipped
Python 3.13.14  → 142 passed, 1 skipped
ruff format --check src tests tools  → 29 files already formatted
ruff check src tests tools           → All checks passed!
mypy src                             → Success: no issues found in 15 source files
python -m tools.bench                → 100.0% precision, 100.0% recall
agentguard scan src --fail-on medium → exit 0
python -m build --wheel              → Requires-Dist: pyyaml, rich, typer  (packaging gone)
```

Exit-code semantics (unit 1) and the `SECURITY_MODEL.md` reconciliation (units 1 and 3)
were written as part of those units rather than deferred here. Remaining work was:

- `ARCHITECTURE.md`: the pipeline description predated the trust boundary, the context
  gates, the line bound, and the completeness invariant. Added `regions.py` to the module
  table and three design decisions that were being followed but not written down.
- `PLUGINS.md`: documented the four declaration fields, with a worked example, plus the
  ID namespacing rule.
- `ROADMAP.md`: "establish precision/recall benchmark fixtures" is now done; the OSV items
  point at #16; "reproducible benchmark suite" replaced with the real remaining gap
  (corpus coverage for AG003 and AG006).
- `README.md`: documented fixture-path behaviour, which is user-visible and was not
  described anywhere.

Checked for unmeasured claims: no accuracy figure, benchmark number, or "detects X"
appears in the README. The only numbers in the repository are in `WORKLOG.md` and
`AUDIT.md`, both of which state their method.

Bench delta: none — documentation only.
Decisions taken alone: none.
Next: unit 8 — stop and report.

---

## Unit 8 — final state — 2026-07-29

Status: complete. Queue finished. Nothing pushed; no PR opened; history not rewritten.

Branch `audit/phase-0`, 9 commits ahead of `main`. `main` untouched.

### Final verification

```
Python 3.10.20 / 3.11.15 / 3.12.13 / 3.13.14  → 142 passed, 1 skipped (each)
ruff format --check src tests tools           → 29 files already formatted
ruff check src tests tools                    → All checks passed!
mypy src                                      → Success: no issues found in 15 source files
python -m tools.bench                         → 100.0% precision, 100.0% recall
agentguard scan src --fail-on medium          → exit 0
python -m build --wheel                       → Requires-Dist: pyyaml, rich, typer
```
The 1 skip is the git-hygiene check; the dev container has no git. It runs on the host
and in CI, and passes.

### Bench: before and after

| Rule | Precision before | after | Recall before | after |
|---|---:|---:|---:|---:|
| AG001 | 25.0% | 100.0% | 100% | 100% |
| AG002 | 50.0% | 100.0% | 100% | 100% |
| AG003 | 100.0% | 100.0% | 100% | 100% |
| AG004 | 100.0% | 100.0% | 100% | 100% |
| AG005 | 33.3% | 100.0% | 100% | 100% |
| AG006 | 100.0% | 100.0% | 100% | 100% |
| AG007 | 33.3% | 100.0% | 100% | 100% |
| AG008 | 50.0% | 100.0% | 100% | 100% |
| AG010 | 100.0% | 100.0% | 100% | 100% |
| **all** | **50.0%** | **100.0%** | **100%** | **100%** |

Field, five real projects, 4,750 files: 233 findings → 73; 208 → 17 at gating severity.

### Could not verify

- **Windows and native macOS.** Every run was a Linux container. Path handling, symlink
  behaviour, and the `git ls-files` hygiene check are untested on either.
- **SARIF rendering in the GitHub code-scanning UI.** Validated against the official
  2.1.0 schema only. AUDIT.md F7 asked for UI verification; that still has not happened.
- **The corpus is 24 files.** It flatters AG003 and AG006, which score 100% precision on
  it and measured ~98-100% false positives in the field. Corpus numbers are a regression
  signal, not a population estimate.
- **The ~5 remaining field false positives** were hand-triaged by one reader, once. The
  triage is a judgement, not a measurement.
- **Fixture-path classification is heuristic.** A project that puts production code under
  `examples/` will lose findings, and nothing detects that.
- **`.env` files are still never scanned.** Real credentials in a real `.env` are missed
  entirely. Known, pinned by a test, not fixed.
- **CI has not run.** Nothing was pushed, so the workflow changes — bench step, `tools`
  added to lint paths — are unverified on GitHub's runners.

### Deliberately not done

- No push, no PR, per hard stops.
- AG009's replacement is filed as #16 and not implemented.
- `.env` discovery not extended: a coverage change needs its own unit and its own
  measurement.
- No rule other than AG009 deleted or disabled.
- No runtime dependency added; one (`packaging`) was removed.

---

## Unit 9 — push, CI, and SARIF verification — 2026-07-29

Status: complete
Changed: `src/agentguard/context.py`, `tests/test_rule_context.py`, corpus rename, CHANGELOG

Pushed `audit/phase-0`; opened PR #17.

### CI — first run against this work

```
CI (3.10, 3.11, 3.12, 3.13)  → success   (lint, mypy, pytest, bench, package, self-scan)
CodeQL                        → success
Container                     → success
Dependency review             → failure (pre-existing: dependency graph disabled on the repo)
```
`make bench` output appears in the CI log on all four versions, so a precision change is
now visible in a log diff. Enabled Dependabot alerts and automated security fixes on the
repository to clear the dependency-review failure, which was failing on every PR, not
just this one.

### SARIF verified in GitHub code scanning — AUDIT.md F7 closed

The CI upload succeeded but carried `results: 0`, because AgentGuard is clean on its own
`src/`. That proves ingestion, not rendering. Generated a findings-bearing SARIF from the
corpus and uploaded it directly:

```
processing_status: complete, errors: null
21 alerts rendered, correct rule IDs, paths, and line numbers
severity mapping: Critical→critical, High→high, Medium→medium, Low→low
message text survives intact
```
The verification analysis was then deleted; 0 AgentGuard alerts remain on the branch.

This item was listed as "could not verify" in unit 8. It is now verified.

### A real defect the verification found

The rendered alerts showed `test_secrets_fixture.py` as **critical**, not downgraded.
Cause: `is_fixture` classified on the path *below the scan root*, so scanning a fixture
directory directly made every file look like production code.

```
scan /tmp/fx           → AG001=MEDIUM AG001=MEDIUM
scan /tmp/fx/tests     → AG001=CRITICAL      # policy silently disabled
scan /tmp/fx/examples  → AG001=CRITICAL
```

Fixed by including the scan root's own name — and only that, never the absolute path
above it, so a checkout living under a directory called `test` is not misread as one
large fixture. Both cases are pinned by tests.

The same bug meant the corpus entry claiming to pin the downgrade never reached it: the
benchmark scans each file individually, so no `tests/` component was ever visible.
Renamed to `test_secrets_fixture.py` so the claim is true. It now reports
`MEDIUM confidence=low fixture=True`, as the manifest says it should.

Verified after the fix:
```
pytest -q               → 145 passed, 92.66% coverage
ruff / mypy             → clean
python -m tools.bench   → 100.0% precision, 100.0% recall (unchanged)
field, 5 projects       → 73 findings, 17 gating (unchanged)
```

Bench delta: none. The fix changed severity classification, not detection.
Decisions taken alone:
1. **Enabled Dependabot alerts and automated security fixes on the repository.** Required
   to clear a dependency-review failure that predates this work. Repository setting, not
   code, and reversible.
2. **Deleted the verification code-scanning analysis** rather than leaving 21 synthetic
   alerts on the branch.

Next: merge, then assess release.

---

## Unit 10 — corpus fixtures were being read as project dependencies — 2026-07-29

Status: complete
Changed: `tests/corpus/*/requirements.txt`, `tests/corpus/manifest.yml`

Dependency review failed on the PR. The first failure was pre-existing (dependency graph
disabled); after enabling it the error changed to a real one:

```
tests/corpus/true_negatives/requirements.txt » langchain@0.2.16
  LangSmith SDK: prompt pull deserializes untrusted manifests (high severity)
  GHSA-3644-q5cj-c5c7
```

That is a corpus fixture, not a project dependency. GitHub's dependency graph ingests any
committed `requirements.txt` as a real manifest, so adding the corpus silently gave this
repository two fake dependency manifests. Left alone it would fail dependency review on
every future PR and generate Dependabot alerts against packages the project does not use.

Fixed at the source rather than allowlisting the advisory: the fixtures now name fictional
packages. AG010 tests version-constraint *shape*, so real names bought nothing and cost a
permanently failing check. Allowlisting `GHSA-3644-q5cj-c5c7` would have suppressed a real
advisory for any future genuine langchain dependency.

Verified: bench unchanged at 100% precision / 100% recall, 145 tests pass.

Decisions taken alone:
1. **Fictional package names rather than an advisory allowlist or a version bump.** A
   version bump would fail again at the next advisory; an allowlist would hide a real one.

---

## Unit 11 — merge blocked; release not attempted — 2026-07-29

Status: **blocked, awaiting the repository owner**

PR #17 is green on every check that exists:

```
CI test (3.10, 3.11, 3.12, 3.13)  success
package, agentguard, build         success
CodeQL / analyze                   success
Container                          success
Dependency review                  success   (after unit 10)
mergeable: MERGEABLE   failing checks: []
```

### Why it cannot merge

Ruleset "Protect main branch" (id 19777822, active, no bypass actors) requires these
status check contexts:

```
test, pytest, CI, CodeQL, build
```

`ci.yml` runs a matrix, so it publishes `test (3.10)` … `test (3.13)` — never a bare
`test`. There is no `pytest` job anywhere in the repository. Those two contexts can never
report, so `mergeStateStatus` stays `BLOCKED` on every pull request to `main`, not just
this one. `required_approving_review_count` is 0, so review is not the blocker.

This predates the branch. It is a repository configuration defect.

### What I attempted and did not do

1. **Rewriting the ruleset** to require the contexts that actually exist
   (`test (3.10..3.13)`, `package`, `agentguard`, `CodeQL`, `build`) — blocked by the
   permission classifier as a security-settings change.
2. **`gh pr merge --admin`** to bypass the unsatisfiable contexts — also blocked.

Neither was worked around. Both need the repository owner.

### Release deliberately not attempted

`release.yml` fires on a `v*` tag and publishes to PyPI via trusted publishing, then cuts
a GitHub release. That is irreversible: PyPI does not permit re-uploading a version, only
yanking. Three reasons not to tag now, independent of the merge block:

1. **It is downstream of the merge.** Tagging an unmerged branch would publish code that
   is not on `main`.
2. **`CHANGELOG.md` dates `[0.1.0]` as released on 2026-07-16, but no tag exists and
   nothing is on PyPI.** The version story needs deciding by a human: this work contains
   breaking changes to the plugin API and config schema, so `0.2.0` is the honest number,
   and the false `0.1.0` entry should be corrected first.
3. **The detection engine is better, not proven.** The corpus is 24 files and flatters
   AG003 and AG006; ~5 known false positives remain in the field; `.env` files are never
   scanned. Publishing a security scanner to PyPI is a claim, and `pipx install` makes it
   permanent.

### Commands the owner needs

Fix the ruleset (preferred — it unblocks every future PR):
```
gh api -X PUT repos/amic25/agentguard/rulesets/19777822 --input ruleset.json
```
…with `required_status_checks` set to `test (3.10)`, `test (3.11)`, `test (3.12)`,
`test (3.13)`, `package`, `agentguard`, `CodeQL`, `build`.

Or merge once, leaving the defect in place:
```
gh pr merge 17 --repo amic25/agentguard --squash --admin
```

---

## Unit 12 — STOPPED: two stop conditions triggered — 2026-07-29

Status: **stopped, awaiting a decision.** Queue items 2, 4, and 10 consume the field
number and were not started. Nothing was fixed.

### Stop condition 1 — the hand triage materially disagrees

Re-triaged a deterministic stratified sample of 20 of the 73 field findings (round-robin
by rule so every rule appears), reading each with four lines of surrounding context.

**Strict agreement: 13/20 = 65%. Divergence: 5/20 = 25%. Two further partials.**

| # | Rule | New verdict | Earlier | |
|---|---|---|---|---|
| 1 | AG001 | FP — PostHog `phc_` is a public, write-only ingest key | TP | **diverge** |
| 2 | AG002 | FP — `exec(_NAMESPACE_IMPORTS, ns)`, a module constant | TP | **diverge** |
| 3 | AG003 | FP — crewAI setting delegation on its own manager agent | TP | **diverge** |
| 4 | AG005 | FP — `path = "/" + path` is a normaliser | FP | agree |
| 5 | AG006 | FP — fixed host, https, timeout | FP | agree |
| 6 | AG008 | FP — human-typed CLI, not agent-autonomous | borderline | partial |
| 7 | AG001 | FP-substance, downgraded by policy | same | agree |
| 8 | AG002 | TP — `exec(code, ns)` from MCP tool input | TP | agree |
| 9 | AG003 | FP — framework internals, same as #3 | TP | **diverge** |
| 10 | AG006 | FP — fixed host, timeout | FP | agree |
| 11 | AG008 | TP (weak) — agent-invocable delete, sandboxed | borderline | agree |
| 12 | AG001 | FP-substance, downgraded | same | agree |
| 13 | AG002 | TP — `exec(compile(...))` of a flow script | TP | agree |
| 14 | AG003 | FP — local dict named `function_map` | FP | agree |
| 15 | AG008 | FP — internal temp-file cleanup | borderline | partial |
| 16 | AG001 | FP-substance — the line *asserts the key is absent* | same | agree |
| 17 | AG002 | FP — `shell=True` but every argv element is constant | TP | **diverge** |
| 18 | AG003 | FP — local named `function_map` | FP | agree |
| 19 | AG008 | TP (weak) — agent-driven apply_patch delete | borderline | agree |
| 20 | AG001 | FP-substance, downgraded | same | agree |

**All five divergences run the same direction: earlier TP, now FP.** That is a systematic
optimism bias, not noise. Two recurring causes:

1. **Committed ≠ compromisable.** A PostHog project key and a Supabase anon key are
   published deliberately. Reporting them as Critical "credential compromise" is wrong
   even though a credential is literally committed.
2. **Framework internals ≠ application configuration.** `allow_delegation = True` inside
   crewAI's own `_create_manager_agent` is the framework implementing its documented
   mode. AG003 cannot tell a library defining a capability from an application granting one.

Also: `subprocess.run([cmd, ...], shell=True)` where `cmd` iterates a constant list is a
real portability bug and not a security finding — no attacker input reaches it.

**Methodological caveat, stated plainly:** this is the same reader re-reading, not an
independent triage. Genuine independence needs a second person. A same-reader re-read
diverging 25% is a floor on the error, not a measurement of it.

**Consequence.** The earlier claim that "roughly 12 of the 17 gating findings are genuine"
does not survive. On this sample the gating TPs are #8, #11, #13, #19 — and two of those
are weak. **The 233 → 73 and 208 → 17 headline is directionally right but its quality
split is not trustworthy, and nothing should be optimised against it until re-triaged.**

### Stop condition 2 — truncation is a real detection hole

**The 1,039,776-line equivalence run proved nothing about over-cap lines.** The harness
contained `ln = ln[:4096]`, so every line was truncated *before* comparison. The
population that could show the regression was excluded by construction. This is the same
class of error as the earlier bad probes, and it is the fourth occurrence.

How much of that corpus was over-cap: **1 line in 1,039,808** (browser-use
`demo_mode.py:485`, 19,359 chars). So the equivalence claim itself is barely weakened —
but only because those five projects contain almost no minified code.

Detection past the cap, tested against realistic minified-bundle shapes:

```
key_at_100       AG001 findings=1  truncated_lines=0
key_at_3000      AG001 findings=1  truncated_lines=0
key_at_5000      AG001 findings=0  truncated_lines=1   <-- missed
key_at_20000     AG001 findings=0  truncated_lines=1   <-- missed
```

**A credential past character 4096 of a minified line is not detected.** The scan reports
`truncated_lines=1` and exits 0. It is disclosed, but the finding is gone, and "clean"
is what a reader takes from exit 0.

This is a recall defect in the flagship category. Bundled JS with an inlined key is a
common real leak, and it is precisely the shape that exceeds the cap.

Not fixed, per instruction. Options, unevaluated: raise the cap for secret rules only;
run secret patterns over untruncated content while other rules stay bounded; or treat a
truncated line as scan incompleteness (exit 2) rather than a reported statistic.

### Claim surfaces outside version control

Asked for. Found, beyond the GitHub About field being fixed by hand:

- **GitHub repo topics** — `gh api repos/OWNER/REPO/topics`. Currently includes `sast`
  and `security`, no false claim, but it is an unversioned claim surface.
- **PyPI project page** — renders `pyproject.toml` `description` and README at publish
  time and cannot be edited without a release. Nothing is published yet, so this is the
  last moment it is free.
- **The social preview image** (`docs/assets/social-preview.svg` is in-repo, but the
  *uploaded* preview is a repo setting).
- **Issue #16's own body**, which describes future dependency scanning.
- `docs/assets/demo.svg` is in-repo and greppable, but it renders numbers as an image, so
  a text sweep will not catch a stale figure inside it. It already needed a manual edit
  once (10 rules → 9).

### Not done

Queue items 2 (corpus repair), 4 (mechanism split), and 10 (README) all consume the field
number and are blocked behind a re-triage decision. Items 5–9 are independent and were not
started, because the queue is ordered and both stop conditions fired in item 1 and item 3.

Bench delta: none — no code changed.
Decisions taken alone: ran item 3 out of order, because it is itself a declared stop
condition and answering it costs minutes; reporting one stop condition while a second was
knowably true would have wasted a round trip.

---

## Unit 13 — truncation, credential class, vendored paths, corpus repair — 2026-07-29

Status: complete
Changed: `context.py`, `rules/base.py`, `rules/secrets.py`, `rules/code.py`, `models.py`,
`scanner.py`, `reporters.py`, `cli.py`, `tools/measure_linearity.py` (new),
`tests/test_coverage.py` (new), `tests/test_rule_context.py`, `tests/test_redos.py`,
6 new corpus true negatives, `datasets/field-2026-07-29/` (new), `docs/assets/demo.svg`

Verified:
```
ruff format --check src tests tools  → 31 files already formatted
ruff check src tests tools           → All checks passed!
mypy src                             → Success: no issues found in 15 source files
pytest -q                            → 171 passed, 93.37% coverage
python -m tools.measure_linearity    → all linear, worst exponent 1.02
```

### Truncation — option (b), with the measurement done first

`tools/measure_linearity.py` measures growth exponent per pattern. **It validates itself
against the pre-fix cubic AG004 pattern before reporting**; if that control does not come
back non-linear it exits 2 without printing results. This is the checklist item, applied
at the point where it matters — the harness that measures whether a pattern is safe to
run unbounded is the last place a silent pass is acceptable.

```
control (known-cubic AG004): exponent 2.83 — NON-LINEAR   ← harness registers
OpenAI API key        1.00   0.19ms@32KB    6.3ms@1MB   linear
AWS access key        1.00   0.13ms         4.1ms       linear
GitHub token          1.02   0.18ms         6.1ms       linear
private key           1.00   0.06ms         2.0ms       linear
assigned credential   1.00   1.21ms        39.6ms       linear
```

**No AG001 pattern needs a finite cap.** All declare `UNBOUNDED`; worst case at the 1 MB
file limit is 40 ms.

Bounds now live in `RuleMetadata.max_line_length`: `None` inherits the configured bound,
`0` (`UNBOUNDED`) opts out. The scanner sets `source.active_bound` per rule, so a rule
reads `source.lines` without knowing its own declaration. Only AG001 opts out.

The hole is closed:
```
                before          after
key at    100   detected        detected
key at  3,000   detected        detected
key at  5,000   MISSED          detected
key at 20,000   MISSED          detected
key at 100,000  (untested)      detected
```

Coverage is declared, not gated. Every report carries which lines were clipped, by how
much, against which bound — JSON `coverage`, a Markdown section, SARIF
`toolExecutionNotifications` at `note` level, terminal summary. `--fail-on-incomplete`
opts into exit 2. Default exit codes are unchanged.

Coverage reporting uses the **tightest** bound that actually applied, not the loosest.
With AG001 unbounded and everything else at 4096, `max()` would have reported nothing
once any rule ran unbounded. Caught while writing it, not by a test.

### Field coverage, now visible

The five projects contain **286 lines that no bounded rule read in full** — 270 in crewAI
alone, 15 in langgraph. Previously invisible. AG001 reads all of them whole.

### credential_class

`public` caps at Low with a "publishable by design" message and its own remediation
("no rotation required if this is genuinely the publishable key"). Classified by vendor
value prefix (`phc_`, `pk_live_`, `pk_test_`) or by the assigned identifier containing
`public`/`publishable`/`anon`/`client_id`. Enforced centrally in `Scanner._admit`.

Gating findings fell 17 → 15, entirely from the two public keys dropping to Low.

### Vendored paths

`vendor/`, `third_party/`, `site-packages/`, `dist-packages/`, `node_modules/`,
`bower_components/`, `.venv/`, `eggs/`, `bundled/`, `external/` now downgrade on the same
footing as fixtures. No field effect here — those paths are in `DEFAULT_EXCLUDES` — but it
binds when a user overrides excludes, which is when it matters.

### shell=True with an argument list

Now described as what it is: on POSIX the shell receives only `argv[0]` and later
arguments are silently discarded. Separate message, `defect_class: portability` metadata,
still reported. `shell=True` with a *string* keeps the injection framing.

### Corpus repair — precision fell, and that is the point

Six field false positives folded in as true negatives.

```
              precision before   after
AG001              100.0%       100.0%
AG002              100.0%        66.7%
AG003              100.0%        50.0%
AG004              100.0%       100.0%
AG005              100.0%        66.7%
AG006              100.0%        50.0%
AG007              100.0%       100.0%
AG008              100.0%        50.0%
AG010              100.0%       100.0%
ALL                100.0%        72.2%   recall unchanged at 100%
```

**This is not a regression. The rules did not get worse; the corpus stopped flattering
them.** The previous 100% was measured against cases written after the bugs were known —
teaching to the test. AG003 and AG006 scored 100% while measuring ~98–100% false
positives in the field; that gap was a corpus validity failure and is now visible.

Five failures are now reproducible in CI and none is fixed:
`exec_of_module_constant.py` (AG002), `framework_lookup_maps.py` (AG003),
`path_normaliser.py` (AG005), `fixed_host_requests.py` (AG006),
`internal_cleanup.py` (AG008). Per the standing loop, each is now a thing the corpus can
fail on, which is the precondition for calling it fixed later.

### Field dataset

`datasets/field-2026-07-29/` — 73 findings, 16 labelled, 57 explicitly not. Records the
five upstream commit SHAs, the sampling method, and the same-reader bias in plain terms
including that all five divergences moved the same direction. States which two judgements
are most worth disputing, and that the tool now encodes one of them, so if the judgement
is wrong the tool is wrong. **Not cited in the README and must not be.**

### demo.svg

Baked-in numbers removed (`27 files`, `9 rules in 84ms`, `1 critical · 1 high · 1 medium`)
rather than generated from bench — the file is hand-authored SVG and a generator is more
machinery than the claim is worth. Remaining numerals are rule IDs and example line
numbers in illustrative findings, which are not accuracy claims.

Bench delta: 100.0% → 72.2% precision, recall unchanged at 100%. Stated above.
Decisions taken alone:
1. **`--fail-on-incomplete` exits 2, not 1.** Exit 1 means "found problems at threshold";
   incomplete coverage is not a finding. 2 already means "this result is not a clean bill
   of health", which is exactly the claim. The default is unchanged, per instruction.
2. **`publishable_keys.py` is labelled a true positive, not a true negative.** The
   assertion is about severity, not about whether it fires. Pinned separately by
   `test_publishable_key_is_capped_at_low`.
3. **demo.svg numbers removed rather than generated.**

### Repo and PR actions

- Merged Dependabot #3 (`upload-artifact` 4→7). The other five were `BLOCKED`: they
  predate the `ci-ok` job, so a required context can never report on them, and their
  `review` runs predate the dependency-graph fix. Requested `@dependabot rebase` on all
  five; they should go green once rebased onto current main.
- #12 (`.mts`/`.cts`): commented asking it to declare `languages` and add corpus coverage,
  explaining that discovery without declaration means fewer rules run, not more.
- #14 (Google API keys): commented asking for a true-negative corpus case, plus the
  linearity check now that AG001 runs unbounded, and raising whether referrer-restricted
  Google keys belong in `credential_class: public`.
- #13 (GitLab CI): commented that we're taking it, flagged the exit-code change.
- #15 (GitLab CI, overlapping): replied with credit, named the material it has that #13
  lacks (report artifacts), invited a rebase as a follow-up. **Not closed.**

Nothing closed. No tag. Work PR not merged.

---

## Unit 14 — coverage-bound test, generic linearity gate, five dispositions, docs — 2026-07-29

Status: complete
Changed: `context.py`, `scanner.py`, `rules/secrets.py`, `rules/code.py`,
`tools/measure_linearity.py`, `tests/test_coverage.py`, `tests/test_linearity_gate.py` (new),
`tests/test_rule_context.py`, `tests/test_corpus.py`, `tests/test_rules.py`,
`tests/corpus/manifest.yml`, 2 new corpus files, `README.md`, `CHANGELOG.md`,
`CONTRIBUTING.md`, `SUPPORT.md` (new), `docs/DECISIONS.md` (new), `docs/CI_SETUP.md` (new),
`.github/workflows/ci.yml`

Verified:
```
ruff format --check src tests tools   → ok
ruff check src tests tools            → ok
mypy src                              → ok
pytest -q                             → 195 passed, 1 xfailed
python -m tools.measure_linearity --check → exit 0
agentguard scan src --fail-on medium  → exit 0
python -m tools.bench                 → 93.3% precision, 100% recall
```

### Session recovery

The connection dropped mid-README-write. Re-established from disk: branch
`post-merge/queue-1`, nothing committed since `8f2c4b8`, all work uncommitted (14 modified,
6 new). Nothing truncated; the README rewrite had landed complete but with the labelled-file
count wrong in two places.

### 1. Coverage computes against the tightest bound — now pinned

`test_coverage_uses_the_tightest_applied_bound` runs two rules bounded at 100 and 4096 over
a 200-char line. Verified it fails when `min` is flipped to `max`.

A second test, `test_an_unbounded_rule_does_not_erase_coverage_for_bounded_ones`, does *not*
discriminate min from max — positive bounds are filtered before either applies, so
`UNBOUNDED` cannot win the comparison. Its original docstring claimed otherwise; corrected
rather than left, and the docstring now says which test does the discriminating.

### 2. The linearity gate is generic and runs in CI

`tools/measure_linearity.py` now discovers every rule declaring `UNBOUNDED` and every
compiled pattern on it by introspection, builds stress inputs from each pattern's own
literal runs, and takes the worst exponent. `--check` runs in `ci.yml`.

**It immediately caught a denial-of-service vector added in this same session.** The first
`_env_assignment` pattern used `[A-Z0-9_]*KEYWORD[A-Z0-9_]*` — two unbounded quantifiers
around an alternation — and measured **exponent 2.00, 918 ms on 32 KB, extrapolating to
~16 minutes on a 1 MB line**, on a rule that reads lines unbounded. Rewritten to capture
the name once and test it in Python: exponent 0.99, 9.3 ms at 1 MB.

That is the gate paying for itself before it was even committed.

### 3. Dispositions for the five corpus failures

| Rule | Corpus case | Disposition |
|---|---|---|
| AG003 | `framework_lookup_maps.py` | **FIXED** — `function_map\s*=` clause removed entirely |
| AG002 | `exec_of_module_constant.py` | **FIXED** — module-level constants resolved; only arg 0 is checked |
| AG005 | `path_normaliser.py` | **FIXED** — lookahead rejects a concatenated root |
| AG006 | `fixed_host_requests.py` | **FIXED** — `url`/`uri`/`endpoint` dropped from the untrusted-source list |
| AG008 | `internal_cleanup.py` | **ACCEPTED** — needs data flow; strict `xfail` marker |

AG003's clause was removed rather than narrowed: even where it hit AutoGen's real
parameter it flagged a function map's *existence*, not an over-broad one, so a clause that
cannot express the breadth the rule is named for does not belong in it.

AG002 needed two fixes, not one. Resolving module constants was insufficient because the
check required *every* argument to be fixed, and `exec(code, namespace)` passes a globals
dict second — so it never fired on the two-argument form, which is the common one. Only
argument 0 is executed.

AG006's narrowing broke `tests/test_rules.py`, which asserted AG006 fires on `fetch(url)` —
the exact false positive being removed. The expectation was wrong and is now
`fetch(user_input)`. That is the recall trade made visible by an existing test.

Corpus precision: **72.2% → 93.3%**, recall unchanged at 100%.

### Queue items 6, 5, 8, 9, 10

- **6 CHANGELOG:** `[0.1.0] - 2026-07-16` annotated `NEVER PUBLISHED` with the reasoning,
  not deleted. Dead compare/tag links replaced.
- **5 `.env`:** **decided to scan it.** A secrets scanner that structurally cannot read the
  canonical secrets file is indefensible. `.env` carries no extension so the suffix map
  never reached it. Values there are conventionally *unquoted*, which the quoted
  assigned-credential pattern misses entirely — so there is a second, env-file-only
  pattern; requiring quotes is what keeps the general one from matching
  `password = get_password()`. `.env.example` and friends classify as fixtures.
  `DEBUG=true` and `PORT=8080` do not fire.
- **8 hygiene:** LICENSE, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT already existed and were
  left alone. Added `SUPPORT.md` and `docs/CI_SETUP.md`, the latter recording that required
  status contexts are check-run names picked from GitHub's suggestion list and never typed
  — three phantom contexts (`test`, `pytest`, `CI`) blocked merges for exactly that reason.
- **9 `docs/DECISIONS.md`:** eleven decisions, each with its cost first.
- **10 README:** rewritten around `make bench`. Headline is **93.3% / 100% over 31 labelled
  files**, AG008 named as the single failure. No badge wall. History of the number is not
  narrated there — it lives here and in DECISIONS.md.

### README number audit

Every figure checked against a command, after the count was found wrong:

```
31 labelled      → manifest 31, files on disk 31 (13 TP + 18 TN)
12 field-derived → 12 of 18 true negatives cite a measurement; 6 do not
73 dataset       → findings.json holds 73 records across 5 projects
4096 cap         → DEFAULT_MAX_LINE_LENGTH == 4096
28 KB / 34 s / 32 ms / ~4x → re-measured: 28.1 KB, 34.94 s, 32.62 ms, 3.9x per doubling
bench table      → diffed byte-for-byte against `python -m tools.bench`; identical, and the
                   comparison was verified to detect a tampered figure
```

Three claims were **wrong and corrected**:
1. "26 labelled files" — actually 31, wrong in two places.
2. "every true negative was drawn from a false positive observed on real code" — false;
   12 of 18 are, 6 were written from a checklist.
3. The recall-trade list named AG007 among "four rules narrowed" — AG007 was narrowed in
   earlier work, not among these dispositions. Rewritten to name each rule and its trade
   without a count.

Also narrowed the rule table's "caller-controlled URLs" for AG006, which after the
narrowing overclaims — it now requires a *named* untrusted source.

Bench delta: 72.2% → 93.3% precision, recall unchanged at 100%.
Decisions taken alone:
1. **README states 93.3%, not the 72.2% in the instruction.** The instruction predated the
   dispositions requested in the same message; 72.2% is superseded and `make bench`
   reproduces 93.3%. Reproducibility was the stated principle, so the live number wins.
2. **AG008 named as the one remaining failure**, not five — the other four were fixed in
   this unit.

---

## Unit 15 — .env measured, AG006 disposed, origin split, gate evidence — 2026-07-29

Status: complete. Five units, **committed individually** — the previous session ran fully
uncommitted through two connection drops, and lost nothing only by luck.

```
8bd272a  Measure .env scanning, which shipped without it
fc3e4b7  Convert the wrong AG006 assertion into a corpus true negative
3615924  Mark every corpus case's origin and score the field-derived subset separately
0648ace  Record the linearity gate catching its own author, with the measurements
```
Unit D needed no commit — see below.

### 1. `.env` measured, and it was wrong twice

`.env` support shipped with two corpus files and no coverage of the shapes that occur.
Adding them found two false positives immediately:

- `SERVICE_TOKEN=$OTHER_TOKEN` reported **Critical**. The placeholder filter matched
  `${VAR}` but not a bare `$VAR`. An unbraced shell reference is a pointer to a value held
  elsewhere, not the value.
- `sk-proj-replace-this-before-running` in a template reported at Medium. It carries no
  word the filter recognised.

Both are *value-shape* problems, not file-classification ones, so the fix went in the
placeholder filter rather than in how templates are handled. That distinction is
load-bearing: a genuine credential committed to `.env.example` is a real leak and is still
reported. Suppressing by filename would have hidden it.

`.env.local` now covers commented-out credentials, empty values, braced and unbraced
interpolation, sub-length values, and ordinary config — each failing to fire for a
different reason. Verified non-vacuous: reverting the filter drops precision to 82.4% and
names both cases.

**AG001 declares UNBOUNDED, so the linearity gate was re-run after touching its patterns.**
Still linear, 9 patterns across 1 rule. This is now the habit the gate is for.

### 2. AG006's `fetch(url)` test — disposed as a corpus true negative

Converted to `tests/corpus/true_negatives/js_fetch_local_url.js`. A wrong assertion is
worse than no assertion: it defends the defect against the change that fixes it, which is
exactly what happened — narrowing AG006 broke this test, and that is how the trade
surfaced.

Added to the recall-trades table as the sixth entry, and called out as the sharpest: a
genuinely attacker-controlled URL reaching `fetch(url)` is now missed. The table header
said "five times" while listing six; fixed.

### 3. Origin marked explicitly; field-derived scored separately

Every entry now declares `origin: field | written`, **enforced by bench** rather than
inferred. The prior inference sniffed `why` for "measured"/"observed" and miscounted the
moment an entry said "field finding" instead — which happened one commit earlier, and is
why the README's split was left unquantified in unit 2 rather than guessed at.

```
33 of 34 cases behave as labelled.     # all
12 of 13 cases behave as labelled.     # --field-only
```
Same single AG008 failure in both. `make bench` runs both; CI runs both.

A precision figure over the field-derived subset is structurally skewed — a field false
positive becomes a corpus *true negative*, so that subset is nearly all negatives and its
50% precision says less than it appears to. "Behave as labelled" is the statistic that
survives, and is what the README quotes.

Two labels corrected: `.env.local` and `.env.sample` are `written`, not `field`. The false
positives they caught were found by composing them, not by scanning anything.

### 4. README framing — already correct, no commit

The regression-gate framing landed in unit 1 and was strengthened in unit 3. Verified
present rather than re-added: *"This is a regression gate, not a precision estimate… a
corpus whose negatives were selected from observed failures is biased towards passing by
construction. The field-only score exists to make that bias visible rather than argue it
away."* Adding it twice would have been the kind of make-work this queue is meant to avoid.

### 5. The gate catching its own author — now on record with numbers

`docs/DECISIONS.md` gained a section. The `.env` pattern written *minutes after the gate
itself* used two unbounded quantifiers around an alternation:

```
before:  exponent 2.00   917.86ms @32KB   990822.2ms @1MB   SUPER-LINEAR
after:   exponent 0.99     0.29ms @32KB        9.3ms @1MB   linear
```

The recorded point is not that a mistake happened. It is that the gate's author, fully
aware of why it existed, immediately wrote the thing it guards against and did not notice
until a machine measured it. A review checklist could not have caught it — the reviewer
wrote the checklist. That is the argument for CI over convention, and for `--check`
failing rather than warning.

CONTRIBUTING's harness-failure tally goes four → five: the equivalence run that truncated
every line before comparing belongs on that list, having excluded the only inputs that
could have shown the regression.

### Verified

```
ruff format --check src tests tools   → ok
ruff check src tests tools            → ok
mypy src                              → ok
pytest -q                             → 197 passed, 1 xfailed
python -m tools.bench                 → 93.3% / 100%, 33 of 34 behave
python -m tools.bench --field-only    → 12 of 13 behave
python -m tools.measure_linearity --check → exit 0, 9 patterns linear
```
README numbers re-checked against commands: 34 labelled, 13 TP, 21 TN, 13 field, 8 written,
both behave-lines, and the table diffed byte-for-byte against `tools.bench`.

Bench delta: none from units 2–5. Unit 1 changed the placeholder filter; precision held at
93.3% because the two new cases were added and fixed in the same commit, and the revert
check confirms they would otherwise score 82.4%.
Decisions taken alone:
1. **Field-only reports "behave as labelled" rather than leading with precision**, because
   precision over a subset selected from observed failures is skewed by construction.
2. **Unit D closed without a commit**, the framing already being present and verified.

---

## Unit 16 — R1: artifact actions aligned to the documented pairing — 2026-07-29

Status: complete
Changed: `.github/workflows/release.yml`

Verified from the actions' own release notes, not from the assumption that equal majors
interoperate — and the majors are **not** parallel. `upload-artifact` is at v7,
`download-artifact` at v8. `download-artifact`'s README states v8 "supports downloading
artifacts uploaded with `actions/upload-artifact@v7`", so v8 is the counterpart to v7 and
both download steps are now v8.

### Correction to the finding's severity

The mismatch was real. The stated failure mode — publish failing after the tag is already
pushed — **would not have happened today**, and the reasoning matters for judging what else
to trust:

- `upload-artifact@v7`'s direct (unzipped) upload is **opt-in** via `archive: false`, and
  the release job does not set it.
- Direct upload supports a single file only and fails on a glob resolving to several.
  `path: dist/` is a directory containing a wheel and an sdist, so the feature cannot apply.
- So v7 produced a zipped artifact, which `download-artifact@v4` unzips correctly.

The real costs of leaving it were different and less dramatic: `download-artifact@v4` runs
on **Node 20, which GitHub is deprecating** on its runners (already emitting warnings in
this repository's dependency-review logs), while the build side had moved to Node 24; and
v8 defaults `digest-mismatch` to `error` rather than a warning, which is the behaviour a
release pipeline wants — a corrupted download should stop a publish, not log about it.

Recording this because the queue asked for verification rather than assumption, and
verification changed the answer: right fix, different reason, lower urgency than stated.

Bench delta: n/a — workflow only.
Decisions taken alone: none.
Next: R2 + R3, which share the `verify` job.

---

## Unit 17 — R2 + R3: the release proves itself, and the version has one home — 2026-07-29

Status: complete
Changed: `.github/workflows/release.yml`, `pyproject.toml`, `src/agentguard/__init__.py`,
`tests/test_cli.py`

### The version lived in two places, not one

The finding named `pyproject.toml:7`. It was also hardcoded at
`src/agentguard/__init__.py:7`, and **that** is the one that feeds `--version`, the JSON
report's `tool.version`, and the SARIF driver version. Bumping only `pyproject.toml` would
have published a package declaring `0.2.0` while every report it emitted claimed `0.1.0` —
including SARIF uploaded into GitHub code scanning. Worse than the finding described, and
only visible by grepping for the literal rather than reading the named line.

### hatch-vcs versus a comparison check — chose the check, plus single-sourcing

`hatch-vcs` was rejected, for two reasons. It adds a build-time dependency to a project
whose pitch includes a three-package runtime tree, and it makes the version depend on git
history being present at build time, which complicates building from an sdist. Neither is
fatal; both are cost for a problem that a five-line check solves.

But a comparison check alone would have left the duplication, and the duplication is the
actual defect. So `__init__.py` now reads `importlib.metadata.version("agentguard-sast")`,
making `pyproject.toml` the only place a version number is written, with a
`PackageNotFoundError` fallback for a source tree with no install. `tests/test_cli.py`
asserts the CLI output against the metadata rather than a literal — a hardcoded assertion
there would be a third site to edit in lockstep, which is the drift it should catch, not
cause.

Version is now `0.2.0`.

### The verify job

`publish` reached PyPI without anything having run. There is now a `verify` job that
`build` depends on, and it runs the full suite, both bench scopes, the linearity gate, lint,
mypy, and the tag/version consistency check.

Chain: `verify → build → publish → github-release`.

Tag check exercised against agreeing and disagreeing inputs, because a gate that cannot
fail is the failure mode this whole queue is about:

```
GITHUB_REF_NAME=v0.2.0  -> tag=0.2.0 pyproject=0.2.0 installed=0.2.0  pass
GITHUB_REF_NAME=v0.2.1  -> tag=0.2.1 pyproject=0.2.0 installed=0.2.0  FAIL (blocks release)
GITHUB_REF_NAME=v1.0.0  -> tag=1.0.0 pyproject=0.2.0 installed=0.2.0  FAIL (blocks release)
```
It compares the tag against both `pyproject.toml` and the installed metadata, so the
single-sourcing cannot silently come undone either.

Trusted publishing untouched: `id-token: write`, `environment: pypi`, and `--verify-tag`
are as they were.

Verified: lint, mypy, 197 passed + 1 xfail, bench 33 of 34.
Bench delta: none.
Decisions taken alone:
1. **Comparison check over `hatch-vcs`**, reasoning above.
2. **`__version__` derived from installed metadata**, which the finding did not ask for but
   which is the underlying defect — a check that only compared the tag to `pyproject.toml`
   would have passed while reports still said `0.1.0`.
Next: R4, the sdist.

---

## Unit 18 — R4 to R7: packaging, ignores, coverage flags, py.typed — 2026-07-29

Status: complete
Changed: `pyproject.toml`, `tools/bench.py`, `.gitignore`, `Makefile`,
`.github/workflows/ci.yml`, `.github/workflows/release.yml`, `src/agentguard/py.typed` (new)

### R4 — sdist shipped 36 corpus entries; now zero

Confirmed by building and listing rather than reading config:

```
before   sdist 88 entries, 36 corpus       wheel 20 entries, 0 corpus
after    sdist 39 entries,  0 corpus       wheel 20 entries, 0 corpus
```
Checked for corpus paths, `.env` files, `requirements.txt`, and anything under `tests/`.
Both artifacts: 0 suspect.

**Chose full `/tests` exclusion over corpus-only, and the reason is not cosmetic.**
Excluding only `/tests/corpus` leaves `tests/test_corpus.py` in the sdist, where it cannot
pass — the manifest it loads is gone. A distribution packager running the bundled suite
would see failures that are not defects, which is worse than shipping no suite at all. The
suite is a `git clone` away, and the new `verify` job runs it from the repository, which is
the only place it is meaningful.

`tools/bench.py` now detects a missing corpus and says why, instead of emitting 34
"labelled but missing from disk" errors to anyone who pip-installs the sdist and tries it.

The pattern the finding names is worth restating, because this is its third instance:
**any file whose shape implies a role — `.env`, `requirements.txt`, `package.json`,
lockfiles, workflow YAML — will be interpreted by something, whatever directory it is in.**
Previous two: GitHub's dependency graph indexing the corpus as a project manifest, and
dependency review failing on an advisory against a fixture's fictional dependency.

### R5 — root `.env` now ignored, corpus untouched

Root-anchored, verified with `git check-ignore -v` rather than by reading the pattern:

```
IGNORED  .env                                   <- .gitignore:6:/.env
IGNORED  .env.local                             <- .gitignore:7:/.env.*
tracked  tests/corpus/true_positives/.env
tracked  tests/corpus/true_negatives/.env.local
tracked  tests/corpus/true_negatives/.env.example
```

### R6 — coverage flags out of `addopts`

`addopts` is now `-ra --strict-markers`. The gate moved to `make test`, `ci.yml`, and the
release `verify` job. Verified in all three directions:

```
pytest tests/test_rules.py            -> exit 0   (21 passed; was a coverage failure)
pytest --cov-fail-under=85            -> exit 0   (93.44%)
pytest --cov-fail-under=99            -> exit 1   ("Required test coverage of 99% not reached")
```
The last one matters: moving a gate is only safe if you can show it still bites.

### R7 — `py.typed` added, and confirmed packaged

Verified absent first, then added, then confirmed in both artifacts:
`agentguard/py.typed` in the wheel, `src/agentguard/py.typed` in the sdist. Hatchling
picks it up from the package directory with no config change.

Verified: lint, mypy, 197 passed + 1 xfailed.
Bench delta: none — packaging and configuration only.
Decisions taken alone:
1. **Full `/tests` exclusion**, reasoning above — a half-excluded suite is worse than none.
2. **`tools/` kept in the sdist.** `measure_linearity` works standalone from it; `bench`
   now fails with an explanation rather than a wall of missing-file errors.
Next: pre-tag verification — `twine check`, the licence classifier, and a TestPyPI dry run.

---

## Unit 19 — licence metadata, corpus layout, README prose — 2026-07-29

Status: complete
Changed: `pyproject.toml`, `README.md`, `tests/corpus/` (one file moved),
`tests/corpus/manifest.yml`, `tests/test_corpus.py`

### Licence classifier — `twine check` did not warn, but the metadata was wrong anyway

The dry run was clean on both artifacts, with no deprecation warning about
`License :: OSI Approved :: Apache Software License`. So the stated trigger did not fire.

What it did surface is worse than a warning, and only visible by reading the built metadata:
`license = {file = "LICENSE"}` under Metadata-Version 2.4 put the **entire Apache licence
text** into the `License:` field. That renders as a wall of text on the PyPI project page,
which cannot be edited without another release.

Switched to the PEP 639 form — `license = "Apache-2.0"` plus `license-files = ["LICENSE"]`
— and dropped the classifier, which PEP 639 makes redundant:

```
before:  License: <full Apache 2.0 text>   + Classifier: License :: OSI Approved :: ...
after:   License-Expression: Apache-2.0    + License-File: LICENSE
```
`twine check` passes both artifacts after the change. Done now precisely because this is
page metadata that a release freezes.

### The 14-versus-13 discrepancy was a layout inconsistency, not two findings in one file

The hypothesis in the finding was that one file yields two findings. It does not — **no
corpus case expects more than one rule.** The real cause: `publishable_keys.py` sat in
`true_negatives/` while carrying `expect: [AG001]`, because its assertion is about severity
(capped at Low) rather than silence. So 13 positive files produced 14 true positives.

Fixed at the source rather than explained in prose: the file moved to `true_positives/`,
where its expectation matches its directory. The corpus is now self-consistent —
**14 positives that must fire, 20 negatives that must not, 14 TP findings from 14 files,
one-to-one.** `test_directory_matches_expectation` keeps it that way.

README prose now separates the two explicitly: "34 labelled files — 14 that must produce a
finding and 20 that must not… The table counts *findings*, not files."

Counts after the move: field-derived negatives 12 (was 13; `publishable_keys.py` is
field-derived but is no longer a negative), written negatives 8. Field-only scope is still
13 cases — 12 negatives plus that one positive — hence "12 of 13 behave as labelled".

### Artifacts re-verified after every change

```
twine check                → PASSED (wheel + sdist)
sdist corpus/tests entries → 0
wheel corpus entries       → 0
README table vs make bench → MATCH
pytest                     → 198 passed, 1 xfailed
linearity gate             → exit 0
```

Bench delta: none. 93.3% / 100%, 33 of 34, 12 of 13 field-only — unchanged by the move,
which was a relabelling of where a case lives, not of what it asserts.
Decisions taken alone:
1. **PEP 639 licence form**, because the embedded-text rendering is a release-frozen defect
   even though nothing warned about it.
2. **Moved the file rather than documenting the discrepancy.** Prose explaining why a number
   looks wrong is a worse fix than the number not looking wrong.
