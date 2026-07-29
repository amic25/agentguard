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
