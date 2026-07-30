# Decisions

Load-bearing calls and what each cost. Reasoning and price, not narrative. A decision
that reads as free was probably not examined closely enough.

---

## Delete AG009 rather than ship a stale advisory database

AG009 bundled three hand-maintained CVE advisories and read only `requirements*.txt` and
`package.json`. Across five real agent projects — 4,750 files — it fired zero times.

**Cost:** AgentGuard reports nothing about vulnerable dependencies, and users who expected
that must run a second tool. Deleting it also retired the ID permanently.

**Why anyway:** a near-empty vulnerability database that never fires is worse than none,
because a clean result implies dependencies were checked. Maintaining a real one is a
data-operations commitment this project has not made. `pip-audit`, `osv-scanner`, and
Dependabot own that data properly. Issue #16 tracks shelling out to them and normalising
into `Finding`, which keeps one report without owning the data.

---

## Make the config trust boundary a type, not a convention

`plugins` is absent from `RepoConfig` entirely, rather than filtered out of it.

**Cost:** a repository owner who wants `plugins`, `disabled_rules`, or
`severity_overrides` must pass `--config` explicitly instead of having it picked up
automatically. That is friction on the common case to defend against the uncommon one.

**Why anyway:** a scanned repository could previously name modules under `plugins:` and
have them imported — arbitrary code execution from the tool's primary advertised use case,
which then reported clean and exited 0. A check can be dropped in a refactor; a field that
does not exist cannot be. `Config.tightened_by` is a meet, so a hostile repository can make
its own scan stricter and never laxer.

---

## Exit code honours completeness, and 2 outranks 1

`0` clean, `1` findings at or above threshold, `2` the scan did not complete.

**Cost:** conditions that used to exit 0 now exit 2, so automation treating 0 as "clean"
sees new failures.

**Why anyway:** it was being misled. A rule crashing on every file exited 0 —
indistinguishable from a clean scan, with CI green over zero coverage. SARIF already
reported this correctly via `executionSuccessful`; only the exit code disagreed. 2 outranks
1 because "the tool broke" and "the tool found problems" need different responses.

---

## Truncation is declared, not gated

Lines beyond a rule's bound are reported in every output format. `--fail-on-incomplete`
opts into exit 2; the default does not gate.

**Cost:** a caller who ignores the coverage section gets an incomplete scan without being
stopped.

**Why anyway:** a bounded read is a known limitation, not a malfunction, and gating on it
by default would fail on any repository containing a minified bundle. Silence was the real
problem — the scan said nothing and exited 0. Naming what was not read is the honest
middle, and the flag exists for callers who need certainty.

---

## Bounds are per rule, and only measured-linear patterns may go unbounded

AG001 declares `UNBOUNDED` and reads whole minified lines. Everything else stays at 4096.

**Cost:** an unbounded rule is a denial-of-service vector if any of its patterns
backtracks. The guarantee has to be enforced forever, for patterns nobody has written yet.

**Why anyway:** a credential at offset 5,000 of a one-line bundle was previously invisible,
and that is a common real leak in exactly the file shape that exceeds the bound. The cost is
paid by `tools/measure_linearity.py --check` in CI, which discovers unbounded rules and their
patterns by introspection and fails the build on anything non-linear.

### Evidence that the gate works: it caught its own author

The `.env` support added in the same session needed a pattern for unquoted values. The first
attempt was:

```python
r"(?i)^\s*(?:export\s+)?[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd)"
r"[A-Z0-9_]*\s*=\s*(?!['\"])(\S{12,})\s*$"
```

Two unbounded `[A-Z0-9_]*` spans around an alternation. It was written, reviewed by its
author, and looked fine. The gate measured it:

```
AG001   _env_assignment   exponent 2.00   917.86ms @32KB   990822.2ms @1MB   SUPER-LINEAR
```

Quadratic. **918 milliseconds on 32 KB, extrapolating to roughly 16 minutes on a single
1 MB line** — on the one rule that reads lines unbounded, in a tool whose entire premise is
running on repositories nobody has read. A hostile file could have hung the scan.

Rewritten to capture the name once and test it in Python instead of matching it with
wildcards:

```
AG001   _env_assignment   exponent 0.99   0.29ms @32KB   9.3ms @1MB   linear
```

The point is not that a mistake was made. It is that a competent author, having just written
the gate and being fully aware of why it existed, then wrote exactly the class of pattern it
guards against — and did not notice until a machine measured it. A review checklist would not
have caught this; the reviewer was the person who wrote the checklist. That is the argument
for the gate being CI rather than a convention, and for `--check` failing the build rather
than printing a warning.

The gate validates itself against a known-cubic pattern before reporting, and refuses to
report at all if that control comes back linear. A measurement tool that cannot demonstrate
it detects the thing it looks for is not evidence of anything.

---

## A credential published by design is capped at Low

PostHog project keys, Stripe publishable keys, and anything named `*_PUBLIC_*` / `*_ANON_*`
report at Low with a "publishable by design" message.

**Cost:** if the classification is wrong — someone commits a secret key whose name says
public — a real compromise is reported at Low. The heuristic is name-and-prefix based and
can be fooled.

**Why anyway:** two of five real projects were reported as having Critical committed
credentials, and both were keys meant to ship in client code. Reporting those as critical
compromise is simply wrong, and a scanner that cries wolf on published keys gets ignored on
real ones. Capped rather than dropped, because the publishable and secret halves are easy
to confuse and it is still worth knowing the value is there.

---

## Test, example, and vendored paths are downgraded, not silenced

Secret findings there report at Medium with low confidence; every other rule is suppressed.

**Cost:** a real credential committed under `tests/` never gates CI. Real code that happens
to live under `examples/` is under-reported. Path-based classification is a heuristic and
a project with an unusual layout loses findings silently.

**Why anyway:** fixtures were the single largest false-positive source measured. Secrets are
downgraded rather than suppressed specifically because live credentials genuinely do reach
test fixtures. Clamped to Medium rather than decremented one step, because `CRITICAL→HIGH`
still trips the default `--fail-on high` and would not have removed any noise at all.

---

## Recall traded for precision, six times

Each was kept because precision was the binding constraint for that rule in the field.

| Change | Recall cost |
|---|---|
| AG005 requires `path` as a whole word | `file_path="/"`, `mount_path="/"` no longer match |
| AG007 dropped bare `function(` | a JS tool registered via a plain function expression is missed |
| Non-secret rules suppressed on fixture paths | AG010 went from 13 field findings to 0 — every hit was under `examples/` |
| `eval`/`exec` over literals and module constants | a literal that is nonetheless dangerous is not reported |
| Call-name resolution returns `""` for non-name receivers | `get_module().system(cmd)` is missed |
| AG006 requires a *named* untrusted source | `fetch(url)` and `requests.get(endpoint)` are missed, whatever the value's provenance |

The alternative in each case was a rule measuring ~100% false positives, which is a rule
nobody leaves switched on.

The AG006 trade is the sharpest of the six, because a genuinely attacker-controlled URL
reaching `fetch(url)` is now missed. It was taken because the rule cannot see provenance at
all: `url` is simply the ordinary name for a variable holding a URL, and treating the name
as evidence produced false positives on every call in the field sample and true positives
on none. Narrowing to names that *do* imply untrusted origin keeps the cases the rule can
actually justify. Closing the gap properly needs data flow, not a longer name list.

This trade was found by an existing test failing: `tests/test_rules.py` asserted AG006
should fire on `fetch(url)`. That assertion was wrong, and a wrong assertion is worse than
no assertion, because it defends the defect against exactly the change that fixes it. It is
now `tests/corpus/true_negatives/js_fetch_local_url.js`.

---

## AG003's `function_map` clause removed rather than narrowed

**Cost:** AutoGen configurations using `function_map` are no longer flagged at all.

**Why anyway:** the clause matched any local variable of that name — measured twice in
openai-agents-python on ordinary dict comprehensions — and even where it hit the real
parameter it flagged a function map's *existence*, not an over-broad one. A clause that
cannot express the breadth the rule is named for does not belong in it. Narrowing to a
keyword-argument context would not have fixed that, only the false matches.

---

## AG008's internal-cleanup false positive accepted, not fixed

`sandbox.fs.delete_file(temp_path)` cleaning up a file the code itself created is reported.

**Cost:** AG008 sits at 50% precision on the corpus, and this is the reason.

**Why anyway:** distinguishing a tool deleting a caller-supplied path from a function
deleting its own temp file needs data flow the rule does not have, and inventing a
name-based heuristic — "`temp_` prefixes are safe" — would be a guess dressed as analysis
and would create a blind spot an attacker could name their way into. Recorded as
`tests/test_rule_context.py::test_ag008_internal_cleanup_is_a_known_limit`, a strict
`xfail`: if it ever passes, the limit closed and this decision needs revisiting.

---

## Scan `.env`, do not declare it out of scope

**Cost:** a new discovery shape, a second credential pattern for unquoted values, and
`.env` files are often gitignored, so a scan of a clean checkout may find nothing while a
developer's working copy is full of live keys.

**Why anyway:** a secrets scanner that structurally cannot read the canonical secrets file
is indefensible. `.env` carries no extension, so the suffix map never reached it. Values
there are conventionally unquoted, which the quoted assigned-credential pattern misses
entirely, so the pattern is env-file-only — requiring quotes is what stops it matching
`password = get_password()` in ordinary source. `.env.example` and friends are treated as
fixtures, since a committed template holds placeholders by convention.

---

## Field numbers are published as a dataset, not cited as a metric

`datasets/field-2026-07-29/` holds 73 findings and 16 labels. The README quotes only
`make bench`.

**Cost:** the most impressive numbers this project has — a 92% reduction in findings that
gate CI — appear nowhere in the README.

**Why anyway:** they are not reproducible from this repository, and the labels have a known
bias: the same reader labelled them twice and disagreed with himself on 5 of 20, with all
five moving the same direction. A number that cannot be re-derived and whose labels are
disputed is a marketing claim. The dataset ships with its method and its bias so the labels
can be argued with, which is worth more than the headline.

---

## A CI-verifiable repository still has a configuration surface CI cannot see

Everything in this project is designed to be checked by a command: rules declare their
context and a schema enforces it, the linearity gate discovers unbounded patterns by
introspection, `make bench` reproduces every published number, and the release proves
itself before publishing. That discipline stops at the repository boundary.

**Cost:** an inspection checklist is the weakest kind of control. It is manual, it goes
stale, and it is only run by someone who remembers to run it.

**Why anyway:** because the alternative is nothing. Four incidents so far, and in every one
the repository looked healthy:

| Setting | What happened |
|---|---|
| Required contexts `test`, `pytest`, `CI` | Every PR sat at `BLOCKED` with all checks green. Three names that no job produces, typed by hand. |
| Dependency graph disabled | `dependency-review.yml` failed on every PR with an error naming a feature, not a defect. |
| About description | Advertised "vulnerable dependencies" for the whole life of the branch that deleted AG009. No signal at all — nothing renders it in CI. |
| PyPI trusted publisher | Not yet triggered. Would fail the OIDC exchange **after** the tag is pushed, spending the version. |

The shape is consistent: **the repository is green, and the thing that is wrong is not in
the repository.** No test can fail, because there is nothing to run.

Two things follow. First, `docs/GITHUB_SETUP.md` carries a checklist naming every such
surface, what depends on it, how to verify it, and whether the breakage is recoverable —
the trusted publisher is marked unrecoverable, because it fails after the tag is spent.
Second, anything that *can* be pulled into version control should be: `ci-ok` exists so a
matrix can change without editing branch protection, which converts a settings problem into
a workflow problem, where CI can see it.

---

## Corpus containment is per-consumer, because no single boundary holds

A security scanner's test corpus is, by construction, indistinguishable from a vulnerable
codebase. It has to be: a corpus that does not look dangerous does not test anything.

**Cost:** containment cannot be solved once. Each new consumer of the repository reads the
corpus in its own way and needs its own exclusion, and the list only grows.

**Why anyway:** because every attempt to draw one boundary has failed. Four readers so far,
each needing a different mechanism:

| Reader | Read the corpus as | Fix |
|---|---|---|
| GitHub dependency graph | project dependency manifests | fictional package names in fixture `requirements.txt` |
| GitHub dependency review | a real advisory against a real dependency | same fix; the advisory was genuine, the dependency was not |
| sdist consumers, package-cache secret scanners | committed credentials | `/tests` excluded from the sdist |
| Ruff | project source with undefined names and unsafe calls | `extend-exclude` in `pyproject.toml` |

Note that no two share a mechanism, and that the directory the files live in was irrelevant
to all four. `tests/corpus/` is a convention this project observes and nothing else does.

### The standing rule

**Any file whose *shape* implies a role — `.env`, `requirements.txt`, `package.json`,
lockfiles, anything under `.github/` — will be interpreted by something, regardless of the
directory it sits in.**

Before adding a corpus file of one of those shapes, check it against the current reader
list above. The check is cheap and the failures are not: the dependency-review incident
surfaced as a genuine high-severity advisory on a pull request, and reading it as a real
finding rather than a corpus artifact would have been entirely reasonable.

Two mitigations are already in place and worth keeping: fixture manifests name fictional
packages and say why in a header comment, and the sdist ships no tests at all. Neither
generalises to the next reader.
