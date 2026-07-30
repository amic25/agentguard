# GitHub project setup

Recommended repository description:

> Open-source AI agent security scanner for secrets, prompt injection, unsafe tools, excessive privileges, system access, APIs, and validation.

Note the omission of "dependencies": AG009 was deleted and AgentGuard does not check
dependencies against vulnerability advisories. The description is a claim surface `grep`
cannot reach — see [Settings outside version control](#settings-outside-version-control).

Recommended topics:

`ai-agents`, `security`, `sast`, `llm-security`, `prompt-injection`, `langchain`, `crewai`, `autogen`, `openai`, `mcp`, `python`, `devsecops`, `security-scanner`

After creating the repository:

1. Enable Issues, Discussions, private vulnerability reporting, dependency graph, Dependabot alerts, and secret scanning where available.
2. Create labels: `bug`, `security`, `rule`, `framework`, `cli`, `reporting`, `documentation`, `good first issue`, `help wanted`, and `blocked`.
3. Create the five issues in [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md).
4. Enable Discussions categories: Announcements, Q&A, Ideas, Show and tell, and Rule proposals.
5. Pin an introductory Discussion using `.github/DISCUSSION_TEMPLATE/welcome.yml` as the guide.
6. Protect `main`: require pull requests, conversation resolution, and the `ci-ok`, `build`, and `CodeQL` checks; disallow force pushes and deletions. **Pick every required context from GitHub's suggestion list, never by typing it** — `test` and `package` are not check-run names and can never report. See below.
7. Configure PyPI trusted publishing for the `release.yml` workflow before tagging a release.
8. Register for the OpenSSF Best Practices badge, then add the assigned project badge.
9. Add a social preview derived from `docs/assets/social-preview.svg`.

Sponsors is intentionally empty until a funding account is created. Update `.github/FUNDING.yml` then publish a sponsor prospectus describing maintenance, response, and roadmap funding goals.


---

## Settings outside version control

Everything below is required by something in this repository and is stored in GitHub or
PyPI settings, where no test, linter, or CI job can see it. Four incidents so far were
caused by one of these being wrong, and in each case the repository looked healthy:

| Incident | Setting | Symptom |
|---|---|---|
| Merges blocked with all checks green | required contexts `test`, `pytest`, `CI` | `BLOCKED`, no failing check |
| Dependency review failed every PR | dependency graph disabled | error naming a feature, not a defect |
| Deleted rule still advertised | About field | no signal at all |
| (pending) | PyPI trusted publisher | fails **after** the tag is spent |

Verify each before a release. The commands assume `gh` is authenticated.

### PyPI trusted publisher — **unrecoverable if wrong**

Required by `release.yml`'s `publish` job. The record on PyPI must match **exactly**:
owner `amic25`, repository `agentguard`, workflow filename `release.yml`, environment
`pypi`. A mismatch fails the OIDC exchange — and it fails *after* the tag has been pushed,
which means the version is spent. PyPI versions can be yanked but never replaced, so the
recovery is a new version number and a permanent gap in the history.

There is no API to read this back. Verify by eye at
`https://pypi.org/manage/project/agentguard/settings/publishing/`, and rehearse the
mechanism first with the TestPyPI dry run (Actions → Release → Run workflow), which has
its own separate publisher record and validates the shape but not this configuration.

### GitHub environments `pypi` and `testpypi`

Referenced by `release.yml`. Verify:

```
gh api repos/amic25/agentguard/environments --jq '[.environments[].name]'
```

If this returns `[]`, neither exists. GitHub creates an environment implicitly on first
use, so a publish can succeed without one — but then it carries **no protection rules**,
and anyone able to push a tag can publish. If the PyPI publisher record names an
environment, the names must match exactly or the OIDC exchange fails.

Recoverable: create the environment and re-run. But not if the tag is already spent.

### Branch ruleset required contexts

Verify against what actually reports:

```
gh api repos/amic25/agentguard/rulesets/19777822 \
  --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'
gh pr checks <any-open-pr>
```

Every required context must appear in the second list. **Always pick them from GitHub's
suggestion list, never type them.** `test`, `pytest`, and `CI` were all typed by hand;
none is a check-run name, so none could ever report, and every pull request sat at
`BLOCKED` with all checks green. `ci-ok` exists precisely so that a matrix can change
without touching this setting. Recoverable, but it blocks all merges until noticed.

### About description and topics

```
gh api repos/amic25/agentguard --jq .description
gh api repos/amic25/agentguard/topics --jq '.names'
```

The description is a claim surface, and it is the one no sweep of the working tree reaches.
It advertised "vulnerable dependencies" after AG009 was deleted. Any claim here must hold
to the same standard as the README: reproducible by `make bench`, or not stated.
Recoverable at any time, but wrong in public until someone looks.

### Dependency graph and Dependabot alerts

```
gh api repos/amic25/agentguard/vulnerability-alerts -i | head -1    # 204 = enabled
```

`dependency-review.yml` fails on every pull request when the graph is disabled, with an
error that reads like a broken workflow rather than a missing setting. Recoverable.

### Social preview image

`docs/assets/social-preview.svg` is in the repository; the uploaded preview is a setting
and is not verifiable by any command. Check by eye at Settings → General → Social preview.
Recoverable.

### Before tagging

1. `gh api .../environments` lists `pypi`.
2. The PyPI publisher record matches owner, repository, workflow, and environment.
3. A TestPyPI dry run has gone green.
4. `gh api .../description` makes no claim `make bench` cannot reproduce.
5. Required contexts all appear in `gh pr checks` on a live pull request.

Only item 2 is unrecoverable. Check it last, and check it twice.
