# AgentGuard — Engineering Audit (Phase 0)

Audit only. No code was changed. Every finding below carries a `file:line`, a classification, and a
reproduction. Ranked by (impact on correctness of scan results) × (likelihood of being hit), with one
deliberate exception noted at F1.

- Commit audited: `4831e3d` on `main`
- Date: 2026-07-29
- Method: full read of all 20 source files (1,474 LOC), plus execution against 5 real OSS agent
  projects and purpose-built hostile inputs.

---

## 0. Repo facts (discovered, not supplied)

These were blank in the brief. I read them out of the repository rather than guessing; each is
sourced so you can correct any that are wrong.

| Fact | Value | Source |
|---|---|---|
| Repo path | `/Users/new/agentguard` (freshly cloned; no prior local copy existed) | — |
| Python | requires `>=3.10`; CI matrix 3.10–3.13 | `pyproject.toml:10`, `.github/workflows/ci.yml:17` |
| Package manager | pip + hatchling backend | `pyproject.toml:1-3`, `Makefile:4` |
| Node | none — JS/TS is *scanned* as text, never executed; no Node toolchain in the repo | `scanner.py:17-30` |
| Test command | `pytest` (via `make test`) | `Makefile:17-18` |
| Lint command | `ruff format --check src tests && ruff check src tests` (via `make lint`) | `Makefile:10-12` |
| Typecheck command | `mypy src` (strict) (via `make type`) | `Makefile:14-15`, `pyproject.toml:78-81` |
| Release status | **Pre-release.** Version `0.1.0`; CHANGELOG dates a `0.1.0`, but there are **no git tags** and no PyPI release. Release workflow triggers on `v*` tags, so it has never fired. | `__init__.py:8`, `git tag` (empty), `.github/workflows/release.yml:4` |
| Existing users | None detectable. 4 commits, no tags, no release. | `git log` |

**Backward-compatibility obligations: effectively none yet.** Nothing has shipped. Rule IDs, CLI
flags, config schema, and output format are all still free to change. This is the single most
valuable fact in the table — the expensive fixes below are cheap *right now* and get permanently
more expensive the moment you tag `v0.1.0`.

**One item I could not derive and did not guess:** your ordering under "What I care about most".
The brief's own Phase 2 ordering (false positives → scanner safety → adoption blockers) is what I
ranked against. Tell me if that is wrong.

**Local environment caveat:** this machine has only Python 3.9.6 (Xcode's), below the project
minimum. All execution below ran in a `python:3.12-slim` container with the repo bind-mounted. I did
not verify behavior on 3.10, 3.11, or 3.13.

---

## 1. Baseline

Established before proposing any change, per the brief.

### Build health — all green

```
$ ruff format --check src tests     20 files already formatted
$ ruff check src tests              All checks passed!
$ mypy src                          Success: no issues found in 14 source files
$ pytest                            46 passed in 1.26s
                                    TOTAL 563 stmts, 90.98% coverage (gate: 85%)
```

### Performance baseline

Python 3.12.13 in Docker, warm page cache, single run each. Peak RSS is `ru_maxrss` of the child.

| Project | Files scanned | Wall time | Peak RSS | Throughput |
|---|---|---|---|---|
| browser-use | 396 | 3.6 s | ~53 MB | 110 files/s |
| langgraph | 548 | 4.8 s | ~58 MB | 114 files/s |
| modelcontextprotocol/python-sdk | 865 | 5.5 s | ~58 MB | 157 files/s |
| openai-agents-python | 891 | 7.5 s | ~58 MB | 119 files/s |
| crewAI | 2,050 | 13.5 s | ~58 MB | 152 files/s |

**Performance is not a problem and should not be optimized.** Memory is flat at ~58 MB regardless of
repo size, throughput is stable at 110–157 files/s, and 2,050 files in 13.5 s is well inside CI
tolerance. The only performance defect is pathological, not general — see F2.

### Detection baseline (hand-triaged)

233 findings across the 5 projects above, every one triaged by reading the cited source line.
"TP" means the finding identifies a real weakness in non-test production code.

| Rule | Findings | TP | FP | FP rate | Note |
|---|---:|---:|---:|---:|---|
| AG001 Hardcoded secret | 63 | 2\* | 61 | **96.8 %** | \*both are *public-by-design* keys |
| AG002 Unsafe execution | 15 | 13 | 2 | **13.3 %** | AST-based; the one good rule |
| AG003 Broad tool permissions | 64 | 1 | 63 | **98.4 %** | |
| AG004 Prompt injection | 0 | 0 | 0 | — | **never fired on any project** |
| AG005 Unrestricted file access | 29 | 0 | 29 | **100 %** | |
| AG006 Risky external API | 4 | 0 | 4 | **100 %** | |
| AG007 Missing validation | 8 | 0 | 8 | **100 %** | |
| AG008 Missing approval gate | 37 | 0 | 37 | **100 %** | |
| AG009 Vulnerable dependency | 0 | 0 | 0 | — | never fired; 3 advisories bundled |
| AG010 Unpinned dependency | 13 | 13 | 0 | 0 % | correct by definition, low value |
| **Total** | **233** | **29** | **204** | **87.6 %** | |

Restricted to the severities that gate CI at the default `--fail-on high`:

> **192 of 208 gating findings are false positives — a 92.3 % false-positive rate.**
> All five projects exit 1. Every one would be disabled on first run.

Self-scan: `agentguard scan src` reports **zero** findings — while `src/` contains the arbitrary-code-
execution defect at F1. Scanning the whole repo (including `tests/`) yields 9 findings, all of which
are the fixture table in `tests/test_rules.py:15-27` — the tool matching strings that *describe*
vulnerabilities. `.agentguard.yml:2` hides this by excluding `tests/**`.

---

## 2. What is already good — leave it alone

Stated explicitly so this audit is not read as uniformly negative. Four subsystems are sound and I
recommend **no work** on them.

1. **Secret redaction is already correct.** This is the thing the brief was most worried about, and
   it is genuinely fine. I planted four live-format credentials and diffed every output path:
   `json`, `markdown`, `sarif`, and `terminal` all emit rule + location only. No raw value appears
   anywhere. The design reason is structural, not accidental: `Finding` (`models.py:38-52`) has no
   snippet/evidence field, so there is no channel for a value to leak through. `secrets.py:45-52`
   passes only the rule kind into the message. Do not "add" redaction; it is already the design.
2. **Symlink handling is correct by default.** `scanner.py:101` skips symlinks, and a symlinked
   *directory* pointing outside the root is not recursed into. Verified with a repo containing both
   `escape_dir -> ../OUTSIDE` and `escape_file.py -> ../OUTSIDE/leaked.py`: scanner saw 1 file and
   reported nothing from outside the root. (The opt-in `follow_symlinks: true` path does escape —
   but that is a symptom of F1, not an independent bug.)
3. **SARIF is schema-valid.** Output validates clean against the official
   `json.schemastore.org/sarif-2.1.0.json` (111 KB schema, `check-jsonschema` exit 0). Gaps are
   additive only (F7), not correctness.
4. **Exit codes are already correct and distinguishable** — 0 clean / 1 findings / 2 tool error,
   verified across clean repo, findings, missing target, and malformed config. They are undocumented,
   not wrong. One real hole at F5.

Also good, briefly: the docs make **no unmeasured accuracy claims** (`README.md:176` and
`docs/SECURITY_MODEL.md` are candid about heuristics and false positives); strict mypy and a 85 %
coverage gate are already enforced in CI; and `AG002` is a genuinely well-built rule.

---

## 3. Findings

### F1 — Scanning an untrusted repo executes arbitrary code from that repo
**Risk · CRITICAL · `plugins.py:22-23`, `config.py:63`, `cli.py:61`**

Ranked #1 on safety, not on the correctness formula. Flagging that deviation explicitly: a scanner
that can be made to execute attacker code is not a scanner, and this is reachable by the tool's
primary advertised use case (CI on a pull request).

`cli.py:61` loads config from the **scan target**:
```python
settings = Config.load(config, target.resolve() if target.is_dir() else target.resolve().parent)
```
`config.py:38` resolves that to `<scanned repo>/.agentguard.yml`; `config.py:63` reads its `plugins:`
list; `plugins.py:22-23` passes those strings straight to `importlib.import_module()`. Importing a
module executes its top-level code.

This directly contradicts the project's own written threat model.
`docs/SECURITY_MODEL.md` states *"The scanned repository is untrusted"* and, separately, *"Explicit
Python plugin modules are trusted code."* Both cannot hold: the untrusted repo chooses the plugins.

**Reproduction** (hostile repo = `.agentguard.yml` + `pwned.py` + any `.py` file):
```yaml
# .agentguard.yml
plugins: [pwned]
```
```python
# pwned.py
import pathlib
pathlib.Path("/poc/PWNED.txt").write_text("arbitrary code executed during scan\n")
rules = []
```
```
$ python -m agentguard scan .
✓ No findings detected.
Scanned 3 files with 10 rules in 2ms · 0 critical, 0 high, 0 medium, 0 low
$ cat /poc/PWNED.txt
arbitrary code executed during scan          # ← payload ran; scan reported clean; exit 0
```
Confirmed executing. The scan reports **clean and exits 0**, so the compromise is silent.

Reachable via `python -m agentguard` (cwd on `sys.path`) and via any module name resolvable in the
environment — a hostile repo can also name an already-installed module for its import side effects
(verified: `plugins: [antigravity]` imports before being rejected for lacking `rules`).

The same root cause lets a hostile repo set `follow_symlinks: true` (verified: reads through a
symlink to a file outside the repo root), raise `max_file_size_kb`, or empty `exclude` — it controls
every resource bound the security model relies on.

*Effort:* 3–5 h. *Blast radius:* 3 files, ~40 lines. Config-schema change (plugins become CLI/env-only,
not repo-file), which needs a CHANGELOG note — but nothing has shipped, so no migration is owed.

---

### F2 — Cubic-time backtracking in AG004 hangs the scanner on one ordinary file
**Risk · HIGH · `rules/code.py:111-113`**

`PromptInjectionRule._patterns[0]` has two greedy `.*` spans separated by an alternation. On a line
with many `prompt=` anchors and no closing match, cost grows ~8× per input doubling (cubic):

| Line length | Match time |
|---|---|
| 1.8 KB | 12 ms |
| 3.6 KB | 76 ms |
| 7.2 KB | 511 ms |
| 14.4 KB | 3.96 s |
| 28.8 KB | **34.4 s** |

**Reproduction** — end-to-end, one 10.8 KB single-line `.js` file, default config:
```
$ agentguard scan .
Scanned 1 files with 10 rules in 1758ms
```
1.7 s for 10.8 KB. The default `max_file_size_kb` is **1024**, so a single permitted file is ~97×
larger; at cubic scaling that is far beyond any CI timeout. Minified JS is the realistic accidental
trigger; `dist/` and `node_modules/` are excluded by default but a checked-in bundle elsewhere is not.

I verified the other rule regexes (AG001, AG003, AG005) are linear on the same probes — this is one
pattern, not a systemic regex problem. Do not rewrite the others.

*Effort:* 2–3 h (rewrite the pattern; add a per-file regex timeout or line-length cap as defense in
depth). *Blast radius:* 1 file. AG004 currently has zero true positives to preserve (see F3).

---

### F3 — Five rules are ~100 % false positives; four shared root causes
**Defect · HIGH · `rules/code.py`, `rules/secrets.py`**

This is the correctness headline: 192 of 208 gating findings are wrong. The causes are four, not
eighteen, and each is independently fixable.

**(a) Rules match definitions and identifiers, not the behaviour they claim.**
`code.py:242` — AG008's `\b(?:send_email|delete_file|deploy|...)\s*\(` matches `def delete_file(` and
`async def deploy(`. *Defining* a function named `delete_file` is not performing an unapproved
high-impact action. This is the majority of AG008's 37 FPs.
`code.py:84` — AG003's `tools\s*=\s*\[[^\]]*(?:shell|...)` matches any *variable named*
`shell_tool` in a list. Its `function_map\s*=` clause matches the ordinary dict comprehension at
`openai-agents-python/src/agents/realtime/session.py:954`. AG003 even flags
`ShellTool(executor=execute_shell, needs_approval=True)` — code that has the exact mitigation.
`code.py:174` — AG006's `fetch\s*\(\s*(?:url|...)` matches `def fetch(url, headers=None)`.

**(b) No language gating — every regex rule runs on every file type.**
`scanner.py:69` runs all rules against all files. AG005 (`code.py:146`), a *filesystem* rule, fires on
`.github/dependabot.yml`'s `directory: "/"` — Dependabot's manifest-discovery key, unrelated to
filesystem access. It fires in 3 of 5 projects. The same pattern flags `streamable_http_path="/"`, an
*HTTP route*, 8 times in python-sdk. `RuleMetadata` (`rules/base.py:13-19`) has no `languages` field.

**(c) No awareness of comments, docstrings, or string literals.**
AG005 fires on the comment `# streamable_http_path="/" means endpoints will be at /api`
(`python-sdk/examples/snippets/servers/streamable_http_multiple_servers.py:41`). AG008 fires inside a
module docstring. AG001 fires on `crew_bearer_token="[Your token: abcdef012345]"` inside a docstring
example. Python files already have a parsed AST available (`context.py:29-38`) that these rules ignore.

**(d) No awareness of test/example/docs files.** The single largest FP source. Of 63 AG001 hits, the
overwhelming majority are fixtures like `api_key="explicit-key"`, `token="expired_token"`,
`password="invalid_password"`, and tutorial files under `docs_src/` and `examples/`.

Two findings are outright defects rather than tuning, each with a 5-line reproduction:

**AG002 — `_name()` drops the receiver, so any `.exec()`/`.eval()` method reads as the builtin.**
`code.py:20-26` returns `node.attr` when the parent resolves to `""`, and a `Call` parent always
resolves to `""`. So `super().exec(...)` becomes `"exec"`.
```python
class Sandbox:
    async def run(self, *command):
        return await super().exec(*command)   # → AG002 Critical (false)
    def other(self):
        return self.client().eval("x")        # → AG002 Critical (false)
```
Both fire. This is AG002's only FP source (2 of 15) and the fix is ~5 lines.

**AG001 — a Python type annotation is read as a credential.**
`secrets.py:29`'s `token\s*[:=]\s*['\"]([^'\"]{12,})['\"]` matches annotations:
```python
def reset(cls, token: "contextvars.Token[Span[Any] | None]") -> None: ...   # → AG001 Critical (false)
```
Real occurrences at `openai-agents-python/src/agents/tracing/scope.py:34` and `:47`.

The entropy gate at `secrets.py:43` cannot help here: per-character Shannon entropy on a short string
is a function of *distinct characters*, not randomness — `"explicit-key"` scores above the 3.0
threshold. The gate is measuring the wrong thing at these lengths.

*Effort:* (a) 4 h · (b) 3 h · (c) 6 h · (d) 3 h · AG002 `_name()` 1 h · AG001 annotation 1 h.
Total ≈ 18 h. *Blast radius:* 2 rule files + `RuleMetadata` (additive field). No output-format change.
**Cannot be started until Phase 1's corpus exists** — otherwise every fix trades unmeasured FPs for
unmeasured FNs.

---

### F4 — AG004 and AG009 have zero recall on real agent code
**Defect · HIGH · `rules/code.py:109-115`, `rules/dependencies.py:17-21`**

AG004 is the flagship rule — prompt injection is the reason this tool exists — and it fired **zero**
times across 5 real agent codebases totalling 4,750 files. Its pattern requires `prompt`/
`system_message`/`instructions`, then `=`, then an f-string interpolating one of 11 hardcoded names,
**all on one physical line**. Real prompt construction is multi-line, uses templates, or names the
variable something else.

AG009 also fired zero times: it bundles 3 advisories (`dependencies.py:17-21`) and only reads
`requirements*.txt` and `package.json` (`dependencies.py:36,41`). Modern agent projects use
`pyproject.toml` / `uv.lock` / `poetry.lock`, none of which it parses.

Note the interaction with F3: AG004's *only* current effect on users is the DoS at F2.

*Effort:* AG004 rewrite 8–12 h (needs the corpus first, and probably AST-based taint-lite for Python).
AG009 is a scope decision, not a bug — see §5.

---

### F5 — A rule that crashes on every file still exits 0
**Defect · MEDIUM · `scanner.py:78-79`, `cli.py:81-87`**

`scanner.py:78` catches per-rule exceptions into `result.errors`. `cli.py` never consults `errors`
when choosing the exit code, so total rule failure is indistinguishable from a clean scan.

**Reproduction** — a plugin rule that raises on every file:
```
$ python -m agentguard scan .
Scanned 3 files with 11 rules in 2ms · 0 critical, 0 high, 0 medium, 0 low
Warning: XX999 failed on app.py: rule exploded
exit=0                                   # ← CI sees green
```
SARIF correctly records `executionSuccessful: false`, so the data model already knows; only the exit
code ignores it. A rule silently broken by a refactor yields a permanently green, zero-coverage gate.

*Effort:* 1–2 h. *Blast radius:* 1 file. Exit-code semantics change (errors → 2), which is a
behavioural change worth a CHANGELOG note.

---

### F6 — An inline suppression silently suppresses the *following* line
**Defect · MEDIUM · `scanner.py:120-128`**

`_suppressed` searches `lines[index-1 : index+1]` — the finding's line **and the one before it**. A
rule-specific suppression therefore also suppresses that rule on the next line.

**Reproduction:**
```python
subprocess.run(a, shell=True)  # agentguard: ignore [AG002]
subprocess.run(b, shell=True)                                  # ← no comment
```
```
reported lines: []          # line 3 suppressed by line 2's comment
```
In a security tool, silently hiding a real finding is the worst failure direction. `README.md:120`
documents "affected or previous line" as intended, so this is arguably by design — but the design
means one suppression covers two lines, which is not what a reader of that sentence expects.

Related and relevant to the brief's adoption-blocker list: a bare `# agentguard: ignore` suppresses
**all** rules, and no justification string is required (`scanner.py:124-127`).

*Effort:* 1 h for the off-by-one; +3 h for required-justification and rule-ID-mandatory suppression.
*Blast radius:* 1 file. Behaviour change; nothing has shipped, so no migration owed.

---

### F7 — SARIF lacks fingerprints and leaks the runner's absolute path
**Limitation · LOW · `reporters.py:96-116`, `reporters.py:130`**

Schema-valid (verified), but two gaps for the GitHub code-scanning path the README advertises:
- No `partialFingerprints` on any result. GitHub uses these to correlate alerts across runs; without
  them alerts close and reopen whenever line numbers shift.
- `reporters.py:130` emits `originalUriBaseIds: {"%SRCROOT%": {"uri": "file:///work/.repro_tmp/"}}` —
  the absolute CI-runner path, embedded in an artifact routinely uploaded to shared storage.

Neither is validated in CI. `.github/workflows/ci.yml:52` uploads SARIF but never schema-checks it.

*Effort:* 2–3 h including a CI validation step. *Blast radius:* 1 file + 1 workflow. Additive.

---

### F8 — `SourceFile.lines` re-splits the file on every access
**Limitation · LOW · `context.py:21-23`**

`lines` is a property calling `self.content.splitlines()` each time. Eight of ten rules call it at
least once per file, so each file is split ~8–10×, plus once more per finding in `_suppressed`.

I am reporting this as a *measured non-problem*: at 110–157 files/s and flat 58 MB RSS it is not
currently hurting anyone. It is a one-line `functools.cached_property` fix that I would take
opportunistically while touching `context.py` for F3(c), and would not schedule on its own.

*Effort:* 15 min. *Blast radius:* 1 line.

---

## 4. Taste — reported, not actioned

Per the brief, listed and left alone.

- `reporters.py:85` builds SARIF rule names via `title.replace(" ", "")` → `"Hardcodedsecret"`.
  Cosmetic in the GitHub UI.
- `models.py:54-63` `to_dict` guards `relative_to` with `suppress(ValueError)`, while
  `reporters.py:48`, `:95`, and `:164` call it unguarded. I could not construct an input that
  reaches the unguarded paths — every yielded path is under `root` by construction — so I am **not**
  claiming a defect. It is an inconsistency, and an invariant worth an assertion rather than a fix.
- `scanner.py:39` instantiates every rule class on construction even when disabled by config.
- `Makefile:26` runs `agentguard scan src --fail-on medium` while CI uses `--fail-on high`.

---

## 5. Recommendation

**Do Phase 1 before touching any rule.** F3 and F4 are the valuable work, and neither can be done
honestly without the corpus and `make bench` — every change would otherwise trade unmeasured false
positives for unmeasured false negatives. The triage table in §1 is the honest starting number:
**87.6 % overall, 92.3 % at gating severity.**

Suggested order, which differs from the brief in one place:

1. **F1** (RCE) — out of order, ahead of the false-positive work. It is 3–5 h, and it is the one
   defect that makes the tool actively dangerous rather than merely noisy.
2. **Phase 1** — corpus + `make bench` + CI wiring. The awkward cases the brief names are exactly the
   ones this audit found in the wild: fixtures, `docs_src/`, docstrings, type annotations, `.env`
   examples, `eval` on a literal, `subprocess` with a fixed argument list.
3. **F3** — the four root causes, measured before and after, one commit per cause.
4. **F5, F6, F2** — small, self-contained, independently testable.
5. **F4** (AG004 rewrite) — the largest single piece; needs the corpus most.
6. **F7, F8** — opportunistic.

### Constraints — what I decline

The brief asked me to justify or decline each of these. I decline all five.

- **Plugin architecture** — already exists (`plugins.py`) and is the F1 attack surface. It solves no
  problem you currently have: there are no third-party rules. I would *narrow* it, not extend it.
- **Second parser backend (libcst / tree-sitter)** — declined for now. Python's stdlib `ast` is
  already parsed and sitting unused at `context.py:29-38`; F3(c) is fixable by *using* it. Revisit
  tree-sitter only if the JS/TS rules (AG003/AG006/AG007, currently 100 % FP) still fail after the
  Python-side AST work — that is a decision for after Phase 1 produces numbers, not before.
- **Rule DSL** — declined. Ten rules do not justify an interpreter, and a DSL would make F3's
  AST-awareness harder to express, not easier.
- **Dependency inversion / additional config formats** — declined. No concrete defect motivates either.
- **New runtime dependencies** — none needed. Every fix above uses stdlib (`ast`, `re`, `tokenize`,
  `hashlib`, `functools`). AG009's expansion is the only item that would tempt a dependency, and I'd
  rather narrow AG009's scope (see below) than take one.

**One scope question for you, at F4/AG009.** The rule bundles 3 hand-maintained advisories and has
zero recall. There are two honest options and they are quite different: (a) delete AG009 and defer to
`pip-audit`/OSV — which `docs/SECURITY_MODEL.md` already recommends — or (b) commit to a real
advisory pipeline, which means an ongoing data-maintenance burden and probably a dependency. I lean
(a): a small sharp tool should not ship a stale vulnerability database. This is a product decision,
not an engineering one, so I am not making it unilaterally.

---

## 6. Verification statement

- Ran: `ruff format --check`, `ruff check`, `mypy src`, `pytest` — all pass on unmodified `main`,
  output quoted in §1.
- Every Defect and Risk above has a reproduction I executed. F1, F2, F5, F6, and the two F3 sub-defects
  were each reproduced from scratch; commands and output are quoted inline.
- **Not verified:** behaviour on Python 3.10, 3.11, 3.13 (only 3.12.13 was available); Windows and
  native macOS path handling (all runs were Linux containers); rendering of the SARIF in the actual
  GitHub code-scanning UI (schema validation only — the brief asks for UI verification and I could
  not perform it).
- The 233-finding triage in §1 is my hand judgement on 5 projects. It is a sample, not a
  ground-truth measurement — which is precisely why Phase 1 exists. Treat the numbers as
  order-of-magnitude, not precise.
