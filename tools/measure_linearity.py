"""Measure how each rule's regexes grow with input length.

A rule may only declare ``max_line_length=UNBOUNDED`` if its patterns are linear. An
unbounded non-linear pattern is a denial-of-service vector — AG004 was cubic and took
34 seconds on 28 KB of one line.

The harness validates itself first against a pattern known to be cubic. If that control
does not come back non-linear, the measurement is not trustworthy and this exits 2
without reporting. A harness that cannot fail is not a harness.

    python -m tools.measure_linearity
"""

from __future__ import annotations

import math
import re
import statistics
import time
from collections.abc import Callable

SIZES = (2000, 4000, 8000, 16000, 32000)
LINEAR_CEILING = 1.35

_SRC = (
    r"(?:request|req|input|user_input|user_message|web_content|document|page|result"
    r"|tool_output|message\.content)"
)
#: AG004 as it stood before the two-step rewrite. Known cubic. Used only as a control.
_KNOWN_CUBIC = re.compile(
    rf"(?i)(?:prompt|system_message|instructions?)\s*=.*"
    rf"(?:f['\"].*\{{{_SRC}\}}|\.format\([^)]*{_SRC}|\+\s*{_SRC})"
)


def _time_once(pattern: re.Pattern[str], text: str) -> float:
    start = time.perf_counter()
    pattern.search(text)
    return time.perf_counter() - start


def growth(pattern: re.Pattern[str], build: Callable[[int], str], sizes=SIZES) -> tuple[float, float]:
    """Return (exponent, seconds at the largest size). Exponent ~1 is linear."""
    times = [min(_time_once(pattern, build(n)) for _ in range(3)) for n in sizes]
    ratios = [
        math.log(times[i] / times[i - 1]) / math.log(sizes[i] / sizes[i - 1])
        for i in range(1, len(sizes))
        if times[i] > 0 and times[i - 1] > 0
    ]
    return (statistics.median(ratios) if ratios else float("nan")), times[-1]


def _verdict(exponent: float) -> str:
    if exponent < LINEAR_CEILING:
        return "linear"
    return "SUPER-LINEAR" if exponent < 2.5 else "NON-LINEAR"


#: One adversarial builder per pattern: near-misses that maximise backtracking.
BUILDERS: dict[str, Callable[[int], str]] = {
    "OpenAI API key": lambda n: ("sk-" + "a" * 19 + " ") * (n // 23),
    "AWS access key": lambda n: ("AKIA" + "B" * 15 + "z") * (n // 20),
    "GitHub token": lambda n: ("ghp_" + "c" * 29 + " ") * (n // 34),
    "private key": lambda n: "-----BEGIN " * (n // 11),
    "assigned credential": lambda n: "api_key = '" + "x" * max(n - 11, 1),
}


def main() -> int:
    exponent, _ = growth(_KNOWN_CUBIC, lambda n: "prompt=f'" * (n // 9) + "{req", SIZES[:4])
    print(f"control (known-cubic AG004): exponent {exponent:.2f} — {_verdict(exponent)}")
    if exponent < 1.5:
        print("HARNESS BROKEN: the control did not register as non-linear. Not reporting.")
        return 2
    print("control registers. Measuring.\n")

    from agentguard.rules.secrets import HardcodedSecretRule

    print(f"{'pattern':24s} {'exponent':>9s} {'32KB':>9s} {'1MB (extrap.)':>14s}  verdict")
    print("-" * 72)
    worst = 0.0
    for kind, pattern in HardcodedSecretRule._patterns:
        exponent, elapsed = growth(pattern, BUILDERS[kind])
        projected = elapsed * (1024 * 1024 / SIZES[-1]) ** exponent
        worst = max(worst, exponent)
        print(
            f"{kind:24s} {exponent:9.2f} {elapsed * 1000:8.2f}ms "
            f"{projected * 1000:13.1f}ms  {_verdict(exponent)}"
        )

    print()
    if worst >= LINEAR_CEILING:
        print(f"At least one pattern is not linear (worst exponent {worst:.2f}).")
        print("AG001 must not declare UNBOUNDED until it is rewritten or given a finite cap.")
        return 1
    print(f"All patterns linear (worst exponent {worst:.2f}). UNBOUNDED is justified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
