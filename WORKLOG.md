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
