# CI configuration notes

Things that cost this project time, written down so they cost it once.

## Required status checks are check-run names, never workflow names

**Always pick required contexts from GitHub's suggestion list. Never type one by hand.**

Three phantom contexts have blocked merges on this repository:

| Typed | What it actually is | Result |
|---|---|---|
| `test` | the matrix publishes `test (3.10)` … `test (3.13)` | never reports |
| `pytest` | a step inside a job, not a job | never reports |
| `CI` | the workflow's `name:`, not a job | never reports |

A required context that no job produces can never be satisfied, so every pull request sits
at `BLOCKED` with all checks green. It fails silently and looks like a permissions problem.
Two separate merges stalled on this before the cause was found.

The suggestion list is populated from contexts GitHub has actually seen, so a name picked
from it is by construction one that reports.

## A matrix makes its own names unstable

`test (3.10)` changes the moment the supported-version list does. Requiring those directly
means editing branch protection every time Python releases.

The `ci-ok` job in `ci.yml` exists for this: it `needs` every other job in the workflow,
runs with `if: always()`, and fails on any dependency result that is not `success` —
covering `failure`, `cancelled`, `skipped`, and any value GitHub adds later, because a gate
that passes on a state it does not recognise is not a gate. Require `ci-ok`; let the matrix
change underneath it.

## Cross-workflow jobs cannot be aggregated

`needs:` only works within one workflow, so `ci-ok` cannot cover CodeQL or the container
build. Those are required separately by their own check-run names.

## A committed `requirements.txt` is a real dependency manifest

GitHub's dependency graph ingests any file with that name, including test fixtures. Adding
a corpus fixture named `requirements.txt` gave this repository two dependency manifests
describing packages it does not use, and dependency review then failed on a genuine
advisory against one of them.

The corpus fixtures therefore use fictional package names, and say so in a header comment.
The same applies to any filename external tools parse by convention: `package.json`,
`pyproject.toml`, lockfiles, and workflow YAML under `.github/`.

## Dependabot PRs predating a new required check

A branch cut before a required job existed cannot report that context, so it blocks
forever. `@dependabot rebase` picks up the new job. Five PRs needed this after `ci-ok` was
added, and one needed a second rebase after earlier merges touched the same file.
