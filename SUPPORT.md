# Support

## Reporting a security issue

Not here. See [SECURITY.md](SECURITY.md) — please do not open a public issue for a
vulnerability in AgentGuard itself.

## A finding looks wrong

This is the most useful kind of report, and the project is set up to receive it.

A false positive is a defect. Open an issue with the smallest snippet that reproduces it
and what you expected instead. Better still, open a pull request adding it to
`tests/corpus/true_negatives/` with a manifest entry explaining why it should not fire —
`make bench` will then fail on it, and no fix counts as complete until it does.

The same applies in reverse: something AgentGuard missed belongs in
`tests/corpus/true_positives/`.

We publish a labelled dataset of real findings at `datasets/field-2026-07-29/`, including
which judgements we are least sure about. Disputing a label there is a genuine
contribution — it says so in that file's README.

## A rule's severity looks wrong

Severity is a judgement and judgements are arguable. Two we have already changed after
being wrong: a credential published by design is not a critical compromise, and a
framework implementing its own documented capability is not an application granting one.
If you think another is miscalibrated, say so.

## Questions about using it

Open a discussion or an issue. Useful things to include: the command, the version
(`agentguard --version`), and the exit code — `0` clean, `1` findings at or above the
threshold, `2` the scan did not complete.

## What this project will not do

- Publish accuracy numbers it cannot reproduce. The only figures in the README come from
  `make bench` against a corpus in this repository.
- Ship a vulnerability advisory database. Dependency scanning is delegated to `pip-audit`,
  `osv-scanner`, and Dependabot, which own that data properly. See issue #16.
- Reuse a retired rule ID. See [docs/RULE_IDS.md](docs/RULE_IDS.md).

## Response times

This is a small project with no support commitment. Security reports get priority; see
SECURITY.md for that path.
