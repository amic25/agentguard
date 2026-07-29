"""Measure detection quality against the labeled corpus.

Emits a per-rule table of true positives, false positives, false negatives, precision,
and recall. No claim about detection quality is admissible without these numbers, and no
rule change should be reviewed without a before-and-after pair of them.

    python -m tools.bench            # table
    python -m tools.bench --json     # machine-readable, for diffing two runs

Exit code is 0 when the corpus was measured, 2 when the corpus itself is inconsistent
(a labelled file missing from disk, or a file on disk with no label). A corpus that has
drifted from its manifest cannot measure anything, so it fails rather than reporting.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agentguard.config import Config
from agentguard.rules import BUILTIN_RULES
from agentguard.scanner import Scanner

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "corpus"
SECTIONS = ("true_positives", "true_negatives")
#: Where a corpus case came from. `field` means it reproduces a false positive or missed
#: finding observed by scanning a real project; `written` means it was composed to cover a
#: case someone thought of. The distinction matters because a corpus whose negatives were
#: all selected from observed failures is biased towards passing, so the two are scored
#: separately rather than blended into one flattering number.
ORIGINS = frozenset({"field", "written"})


@dataclass
class Tally:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    fp_locations: list[str] = field(default_factory=list)
    fn_locations: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        denominator = self.true_positives + self.false_positives
        return None if denominator == 0 else self.true_positives / denominator

    @property
    def recall(self) -> float | None:
        denominator = self.true_positives + self.false_negatives
        return None if denominator == 0 else self.true_positives / denominator


def load_manifest() -> tuple[dict[Path, set[str]], dict[Path, str]]:
    """Return (expectations, origins). Both keyed by path."""
    raw = yaml.safe_load((CORPUS / "manifest.yml").read_text(encoding="utf-8"))
    labels: dict[Path, set[str]] = {}
    origins: dict[Path, str] = {}
    problems: list[str] = []
    for section in SECTIONS:
        for name, entry in (raw.get(section) or {}).items():
            path = CORPUS / section / name
            if not path.exists():
                problems.append(f"labelled but missing from disk: {section}/{name}")
                continue
            if not (entry or {}).get("why", "").strip():
                problems.append(f"no `why` given for {section}/{name}")
            origin = (entry or {}).get("origin")
            if origin not in ORIGINS:
                problems.append(
                    f"{section}/{name}: `origin` must be one of {', '.join(sorted(ORIGINS))}, got {origin!r}"
                )
            origins[path] = origin if origin in ORIGINS else "written"
            labels[path] = set(entry.get("expect") or [])

    on_disk = {path for section in SECTIONS for path in (CORPUS / section).rglob("*") if path.is_file()}
    for path in sorted(on_disk - set(labels)):
        problems.append(f"on disk but unlabelled: {path.relative_to(CORPUS)}")

    if problems:
        for problem in problems:
            print(f"corpus error: {problem}", file=sys.stderr)
        raise SystemExit(2)
    return labels, origins


def measure(
    labels: dict[Path, set[str]],
) -> tuple[dict[str, Tally], list[str], list[str], list[str]]:
    tallies: dict[str, Tally] = defaultdict(Tally)
    for rule in BUILTIN_RULES:
        tallies[rule.metadata.id] = Tally()

    scan_errors: list[str] = []
    undiscovered: list[str] = []
    misbehaving: list[str] = []
    for path, expected in sorted(labels.items()):
        result = Scanner(Config()).scan(path)
        scan_errors.extend(result.errors)
        if result.files_scanned == 0:
            # File discovery never opened it, so it proves nothing either way. Counting
            # this as a clean negative would credit the tool for coverage it lacks.
            undiscovered.append(path.relative_to(CORPUS).as_posix())
            continue
        fired = defaultdict(list)
        for finding in result.findings:
            fired[finding.rule_id].append(finding.location.line)

        rel = path.relative_to(CORPUS).as_posix()
        if set(fired) != expected:
            misbehaving.append(rel)
        for rule_id, lines in fired.items():
            if rule_id in expected:
                tallies[rule_id].true_positives += 1
            else:
                tallies[rule_id].false_positives += 1
                tallies[rule_id].fp_locations.append(f"{rel}:{lines[0]}")
        for rule_id in expected - set(fired):
            tallies[rule_id].false_negatives += 1
            tallies[rule_id].fn_locations.append(rel)
    return dict(tallies), scan_errors, undiscovered, misbehaving


def _pct(value: float | None) -> str:
    return "  —  " if value is None else f"{value * 100:5.1f}%"


def render(
    tallies: dict[str, Tally],
    scan_errors: list[str],
    undiscovered: list[str],
    total: int,
    subset: bool,
    misbehaving: list[str],
) -> None:
    scope = "field-derived cases only" if subset else f"{total} labelled cases"
    print(f"AgentGuard detection benchmark — {len(BUILTIN_RULES)} rules, {scope}\n")
    print("| Rule  |  TP |  FP |  FN | Precision | Recall |")
    print("|-------|----:|----:|----:|----------:|-------:|")
    totals = Tally()
    for rule_id in sorted(tallies):
        tally = tallies[rule_id]
        totals.true_positives += tally.true_positives
        totals.false_positives += tally.false_positives
        totals.false_negatives += tally.false_negatives
        print(
            f"| {rule_id} | {tally.true_positives:3d} | {tally.false_positives:3d} | "
            f"{tally.false_negatives:3d} | {_pct(tally.precision):>9} | {_pct(tally.recall):>6} |"
        )
    print(
        f"| **all** | {totals.true_positives:3d} | {totals.false_positives:3d} | "
        f"{totals.false_negatives:3d} | {_pct(totals.precision):>9} | {_pct(totals.recall):>6} |"
    )

    for rule_id in sorted(tallies):
        tally = tallies[rule_id]
        for location in tally.fp_locations:
            print(f"\n  FP  {rule_id}  {location}", end="")
        for location in tally.fn_locations:
            print(f"\n  FN  {rule_id}  {location}", end="")
    if any(t.fp_locations or t.fn_locations for t in tallies.values()):
        print()

    # Precision over a subset selected from observed failures is structurally skewed - the
    # field-derived cases are nearly all negatives, because a field false positive becomes a
    # true negative here. How many behave as labelled is the statistic that survives that.
    behaving = total - len(misbehaving)
    print(f"\n{behaving} of {total} cases behave as labelled.")
    for name in misbehaving:
        print(f"  does not: {name}")

    if undiscovered:
        print(
            f"\n{len(undiscovered)} corpus file(s) never opened by file discovery. These measure"
            "\nnothing, and the same blind spot applies to real repositories:"
        )
        for name in undiscovered:
            print(f"  {name}")

    if scan_errors:
        print(f"\n{len(scan_errors)} scan error(s) — the measurement is incomplete:")
        for error in scan_errors:
            print(f"  {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--field-only",
        action="store_true",
        help="score only cases derived from scanning real projects, excluding composed ones",
    )
    args = parser.parse_args()

    labels, origins = load_manifest()
    if args.field_only:
        labels = {path: expected for path, expected in labels.items() if origins[path] == "field"}
    tallies, scan_errors, undiscovered, misbehaving = measure(labels)
    if args.json:
        print(
            json.dumps(
                {
                    "rules": {
                        rule_id: {
                            "tp": t.true_positives,
                            "fp": t.false_positives,
                            "fn": t.false_negatives,
                            "precision": t.precision,
                            "recall": t.recall,
                            "false_positives": t.fp_locations,
                            "false_negatives": t.fn_locations,
                        }
                        for rule_id, t in sorted(tallies.items())
                    },
                    "cases": len(labels),
                    "misbehaving": misbehaving,
                    "scan_errors": scan_errors,
                    "undiscovered": undiscovered,
                },
                indent=2,
            )
        )
    else:
        render(tallies, scan_errors, undiscovered, len(labels), args.field_only, misbehaving)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
