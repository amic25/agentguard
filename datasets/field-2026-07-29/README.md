# Field measurement — 2026-07-29

73 findings from scanning five real open-source AI agent projects. Published so the
labels can be disputed rather than taken on trust.

**These numbers are not cited in the project README, and should not be.** They are not
reproducible from this repository — they depend on five external repositories at
particular commits — and the labelling has a known bias described below. The only
accuracy figures AgentGuard publishes are the ones `make bench` reproduces from
`tests/corpus/`.

## Method

Each project was cloned at the commit below and scanned with default configuration:

```
agentguard scan <project> --format json --fail-on none
```

| Project | Commit |
|---|---|
| `browser-use` | `f0aa3a8bb03779c71a5aa262d389e3bfe6b77cdc` |
| `langgraph` | `41341457342327166d72fc11952ab28fb61ec0bf` |
| `python-sdk` | `6f69a3758ebf2ee55ce050f58b470ce11af71133` |
| `openai-agents-python` | `e75cdd2e2c76f7930d894c6f46174cb091fc724f` |
| `crewAI` | `f15844b21966e35dff2f656ce8724b985703043c` |

`findings.json` holds every finding with `project`, `rule_id`, `severity`, `confidence`,
`path`, `line`, and — where one was assigned — a `label` and `rationale`.

Labels: `true_positive`, `true_positive_weak`, `false_positive`, or `null` for unlabelled.

## Coverage of the labelling

**16 of 73 are labelled. 57 are not.** The labelled set is a deterministic stratified
sample drawn round-robin by rule, so every rule appears, plus the findings that gate CI
at the default threshold. It is not a random sample and the unlabelled remainder should
not be assumed to follow the same distribution.

## Known bias — please read before using these labels

**All labels were assigned by the same reader, twice, months apart in effort but not in
perspective.** The second pass disagreed with the first on 5 of 20 findings — 25% — and
**every one of those five moved the same direction: previously true positive, now false
positive.**

That is a systematic optimism bias in the first pass, and the second pass may carry its
own in the other direction. A same-reader re-read diverging 25% establishes a floor on
the error, not a measurement of it.

Two judgements did most of the work and are the ones most worth arguing with:

1. **A committed credential that is published by design is not a compromise.** PostHog
   project keys and Supabase anon keys are meant to ship. Labelled false positive despite
   a credential being literally committed. AgentGuard now reports these at Low rather
   than Critical, so the tool encodes this judgement — if it is wrong, the tool is wrong.
2. **A framework implementing its own documented capability is not an application
   granting one.** `allow_delegation = True` inside crewAI's own `_create_manager_agent`
   is labelled false positive. Someone could reasonably argue a library shipping a
   permissive default deserves a finding.

## Disputing a label

Open an issue or a PR editing `findings.json`. A label changed with a stated reason is
strictly more useful than the current one. Labelling any of the 57 unlabelled findings is
the single most valuable contribution to this dataset.
