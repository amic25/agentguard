# Rule identifier policy

A rule ID is not a label. It is written into places AgentGuard does not control and cannot
migrate:

- `disabled_rules` and `severity_overrides` in operator configuration,
- `# agentguard: ignore [AG00X]` suppression comments in source files,
- stored SARIF alerts and their dismissal state in GitHub code scanning,
- baseline files, dashboards, tickets, and audit evidence.

Every one of those is a claim about a *specific check*. If the meaning behind an ID changes,
each of those claims silently becomes a claim about something else — a suppression written to
excuse one thing starts excusing another, and nobody is told. That is a security failure with
no error message, so the identifier is treated as a public API with stricter rules than the
code it names.

## Guarantees

**An ID is never reused.** When a rule is retired its identifier is retired with it, permanently.
A future check, however similar, gets a new number. This is the rule that matters most: reuse is
the only change that can turn an existing suppression into a silent hole.

**An ID is never silently renamed.** If a rule's identifier must change, the old ID is aliased to
the new one, both are honoured in configuration and suppressions, and the alias is documented
here and in `CHANGELOG.md`. The alias is removed only in a major version.

**An ID's meaning does not widen.** Narrowing what a rule matches (fewer false positives) is a
normal fix. Widening it so the ID covers a materially different weakness is a new rule, because
anyone who suppressed the old meaning did not consent to the new one.

**Severity may change; identity may not.** Severity and confidence are tuning. They are noted in
`CHANGELOG.md` when they move, but they do not require a new ID.

## Namespacing

`AG###` is reserved for built-in rules. Third-party rules distributed as plugins must use their
own prefix — `ACME001`, not `AG011` — so that adding a built-in rule can never collide with a
rule someone else shipped. `Scanner` rejects duplicate IDs at construction time.

## Retired identifiers

| ID | Rule | Retired | Reason |
|---|---|---|---|
| `AG009` | Known vulnerable dependency | Unreleased | Bundled three hand-maintained advisories and matched only `requirements*.txt` and `package.json`. Measured zero true positives and zero false positives across five real agent projects (4,750 files) — it never fired at all. Shipping a stale, near-empty vulnerability database invites false confidence, and maintaining a real one is a data-operations commitment this project has not made. Dependency scanning is delegated to `pip-audit`, `osv-scanner`, and Dependabot, as `docs/SECURITY_MODEL.md` already recommended. |

Retired IDs stay in this table permanently. `AG009` will not be issued again.

## Adding a rule

Take the next unused `AG###`. Do not fill gaps left by retired rules.
