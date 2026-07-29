"""Measure how each rule's regexes grow with input length, and gate on it.

A rule may only declare ``max_line_length=UNBOUNDED`` if its patterns are linear. An
unbounded non-linear pattern is a denial-of-service vector: AG004 was cubic and took 34
seconds on 28 KB of a single line, and the file-size limit permits 1 MB.

This discovers every rule declaring ``UNBOUNDED`` and every compiled pattern on it, so a
contributor adding a pattern is covered without editing this file. Run with ``--check``
in CI: it exits non-zero if any unbounded rule owns a pattern that is not linear.

The harness validates itself first against a pattern known to be cubic. If that control
does not come back non-linear, the measurement is not trustworthy and nothing is
reported. A harness that cannot fail is not a harness — and this one is what stands
between a contributor's regex and an unbounded read.

    python -m tools.measure_linearity            # table
    python -m tools.measure_linearity --check    # exit 1 if any unbounded rule is unsafe
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
import time
from collections.abc import Callable, Iterator

from agentguard.context import UNBOUNDED
from agentguard.rules import BUILTIN_RULES
from agentguard.rules.base import Rule

SIZES = (2000, 4000, 8000, 16000, 32000)
LINEAR_CEILING = 1.35
MAX_FILE_BYTES = 1024 * 1024

_SRC = (
    r"(?:request|req|input|user_input|user_message|web_content|document|page|result"
    r"|tool_output|message\.content)"
)
#: AG004 as it stood before the two-step rewrite. Known cubic. Control only.
_KNOWN_CUBIC = re.compile(
    rf"(?i)(?:prompt|system_message|instructions?)\s*=.*"
    rf"(?:f['\"].*\{{{_SRC}\}}|\.format\([^)]*{_SRC}|\+\s*{_SRC})"
)

#: Literal runs inside a regex source, used to build inputs that almost match.
_LITERAL_RUN = re.compile(r"[A-Za-z0-9_/:.-]{3,}")


def _time_once(pattern: re.Pattern[str], text: str) -> float:
    start = time.perf_counter()
    pattern.search(text)
    return time.perf_counter() - start


def growth(
    pattern: re.Pattern[str], build: Callable[[int], str], sizes: tuple[int, ...] = SIZES
) -> tuple[float, float]:
    """Return (exponent, seconds at the largest size). Exponent ~1 is linear."""
    times = [min(_time_once(pattern, build(n)) for _ in range(3)) for n in sizes]
    ratios = [
        math.log(times[i] / times[i - 1]) / math.log(sizes[i] / sizes[i - 1])
        for i in range(1, len(sizes))
        if times[i] > 0 and times[i - 1] > 0
    ]
    return (statistics.median(ratios) if ratios else float("nan")), times[-1]


def stress_inputs(pattern: re.Pattern[str]) -> Iterator[tuple[str, Callable[[int], str]]]:
    """Adversarial builders derived from the pattern itself.

    Backtracking blows up on input that *nearly* matches, so the useful inputs are built
    from the pattern's own literal runs, repeated, with the match denied at the end.
    Generic by construction: a pattern added tomorrow is stressed the same way.
    """
    yield "filler", lambda n: "a" * n
    yield "quotes", lambda n: "'\"" * (n // 2)
    literals = sorted(set(_LITERAL_RUN.findall(pattern.pattern)), key=len, reverse=True)[:3]
    for literal in literals:
        yield f"repeat {literal!r}", lambda n, lit=literal: (lit * (n // len(lit) + 1))[:n]
        yield (
            f"repeat {literal!r}+sep",
            lambda n, lit=literal: ((lit + " ") * (n // (len(lit) + 1) + 1))[:n],
        )
        yield (
            f"near-miss {literal!r}",
            lambda n, lit=literal: ((lit + '="') * (n // (len(lit) + 2) + 1))[:n],
        )


def worst_growth(pattern: re.Pattern[str]) -> tuple[float, float, str]:
    """Worst (exponent, time, label) over every stress input for this pattern."""
    worst = (0.0, 0.0, "none")
    for label, build in stress_inputs(pattern):
        exponent, elapsed = growth(pattern, build)
        if not math.isnan(exponent) and exponent > worst[0]:
            worst = (exponent, elapsed, label)
    return worst


def patterns_of(rule: type[Rule]) -> Iterator[tuple[str, re.Pattern[str]]]:
    """Every compiled regex reachable as a class attribute, including inside tuples.

    Introspection rather than a registry, so a contributor does not have to remember to
    declare a new pattern in order for it to be gated.
    """
    for name, value in vars(rule).items():
        if isinstance(value, re.Pattern):
            yield name, value
        elif isinstance(value, tuple | list):
            for index, item in enumerate(value):
                if isinstance(item, re.Pattern):
                    yield f"{name}[{index}]", item
                elif isinstance(item, tuple | list):
                    for sub in item:
                        if isinstance(sub, re.Pattern):
                            yield f"{name}[{index}]", sub


def _verdict(exponent: float) -> str:
    if exponent < LINEAR_CEILING:
        return "linear"
    return "SUPER-LINEAR" if exponent < 2.5 else "NON-LINEAR"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure regex growth for unbounded rules.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any rule declaring UNBOUNDED owns a non-linear pattern",
    )
    args = parser.parse_args()

    exponent, _ = growth(_KNOWN_CUBIC, lambda n: "prompt=f'" * (n // 9) + "{req", SIZES[:4])
    print(f"control (known-cubic AG004): exponent {exponent:.2f} — {_verdict(exponent)}")
    if exponent < 1.5:
        print("HARNESS BROKEN: the control did not register as non-linear. Not reporting.")
        return 2
    print("control registers. Measuring.\n")

    unbounded = [r for r in BUILTIN_RULES if r.metadata.max_line_length == UNBOUNDED]
    if not unbounded:
        print("No rule declares UNBOUNDED. Nothing to gate.")
        return 0

    header = f"{'rule':7s} {'pattern':22s} {'exp':>5s} {'32KB':>9s} {'1MB':>10s}  worst input"
    print(header)
    print("-" * len(header))
    failures: list[str] = []
    for rule in unbounded:
        for name, pattern in patterns_of(rule):
            exponent, elapsed, label = worst_growth(pattern)
            projected = elapsed * (MAX_FILE_BYTES / SIZES[-1]) ** exponent
            print(
                f"{rule.metadata.id:7s} {name:22s} {exponent:5.2f} {elapsed * 1000:8.2f}ms "
                f"{projected * 1000:9.1f}ms  {label} [{_verdict(exponent)}]"
            )
            if exponent >= LINEAR_CEILING:
                failures.append(
                    f"{rule.metadata.id}.{name} — {_verdict(exponent)}, exponent {exponent:.2f}, "
                    f"worst on {label}"
                )

    print()
    if failures:
        print("Declared UNBOUNDED but not linear:")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nEither rewrite the pattern, or give the rule a finite max_line_length until it "
            "is rewritten.\nAn unbounded non-linear pattern is a denial-of-service vector."
        )
        return 1 if args.check else 0
    checked = sum(1 for r in unbounded for _ in patterns_of(r))
    print(f"All linear: {checked} pattern(s) across {len(unbounded)} unbounded rule(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
