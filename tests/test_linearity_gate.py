"""The gate that decides whether a pattern may run unbounded.

A rule declaring UNBOUNDED reads whole minified lines, so a non-linear pattern there is a
denial-of-service vector. `tools.measure_linearity --check` runs in CI to enforce that for
patterns nobody has written yet. These tests check the gate itself can fail — the measure
is only worth having if it registers a bad pattern, and it is the last thing standing
between a contributor's regex and an unbounded read.
"""

from __future__ import annotations

import re

import pytest
from tools import measure_linearity as gate

from agentguard.context import UNBOUNDED
from agentguard.rules import BUILTIN_RULES


def test_the_known_cubic_control_is_classified_non_linear() -> None:
    """If this stops failing, every result the gate reports is worthless."""
    exponent, _ = gate.growth(gate._KNOWN_CUBIC, lambda n: "prompt=f'" * (n // 9) + "{req", gate.SIZES[:4])
    assert exponent >= 1.5, f"the control measured {exponent:.2f}; the harness is broken"
    assert gate._verdict(exponent) in {"SUPER-LINEAR", "NON-LINEAR"}


def test_a_linear_pattern_is_classified_linear() -> None:
    exponent, _ = gate.growth(re.compile(r"\bAKIA[A-Z0-9]{16}\b"), lambda n: "AKIA" * (n // 4))
    assert gate._verdict(exponent) == "linear"


def test_generic_stress_inputs_are_derived_from_the_pattern() -> None:
    """A pattern added tomorrow is stressed without editing the tool."""
    labels = [label for label, _ in gate.stress_inputs(re.compile(r"secret\s*=\s*['\"]"))]
    assert "filler" in labels
    assert any("secret" in label for label in labels), "literal runs must be mined from the source"


def test_patterns_are_discovered_by_introspection() -> None:
    """Not a hand-maintained list: a new pattern attribute is picked up automatically."""
    from agentguard.rules.secrets import HardcodedSecretRule

    names = {name for name, _ in gate.patterns_of(HardcodedSecretRule)}
    assert len(names) >= 6, f"expected every compiled pattern, found {names}"
    assert "_placeholder" in names, "bare attributes must be found, not just tuples"
    assert any(n.startswith("_patterns[") for n in names), "patterns inside tuples must be found"


def test_a_new_pattern_on_an_unbounded_rule_is_covered() -> None:
    """The regression this gate exists for: someone adds a pattern and nothing checks it."""
    from agentguard.rules.secrets import HardcodedSecretRule

    class WithNewPattern(HardcodedSecretRule):  # type: ignore[misc]
        _added_later = re.compile(r"\bnew-[A-Za-z0-9]{10,}\b")

    names = {name for name, _ in gate.patterns_of(WithNewPattern)}
    assert "_added_later" in names


def test_every_unbounded_builtin_is_currently_linear() -> None:
    """The live guarantee, asserted in the ordinary test run as well as in CI."""
    unbounded = [r for r in BUILTIN_RULES if r.metadata.max_line_length == UNBOUNDED]
    assert unbounded, "AG001 is expected to declare UNBOUNDED"
    for rule in unbounded:
        for name, pattern in gate.patterns_of(rule):
            exponent, _, label = gate.worst_growth(pattern)
            assert exponent < gate.LINEAR_CEILING, (
                f"{rule.metadata.id}.{name} measured {exponent:.2f} on {label}; it must not declare UNBOUNDED"
            )


@pytest.mark.parametrize(
    ("exponent", "expected"),
    [(0.9, "linear"), (1.0, "linear"), (1.34, "linear"), (1.4, "SUPER-LINEAR"), (2.9, "NON-LINEAR")],
)
def test_verdict_boundaries(exponent: float, expected: str) -> None:
    assert gate._verdict(exponent) == expected
