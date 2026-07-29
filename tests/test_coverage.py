"""Per-rule line bounds, and coverage reported rather than assumed.

A credential inlined in a minified bundle sits past any sane per-line bound, and that is
a common real leak. The secret rule therefore reads lines whole while every other rule
stays bounded, and what was clipped is declared in every report.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.config import Config
from agentguard.context import DEFAULT_MAX_LINE_LENGTH, UNBOUNDED, SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules.base import Rule, RuleMetadata
from agentguard.scanner import Scanner

runner = CliRunner()

KEY = "sk-proj-Qw8dLm2VtBnKcXrJf7HsPu4Ay6Ez1Nio"
FILLER = '!function(e,t){"object"==typeof exports?module.exports=t():e.x=t()}(this,function(){});'


def _bundle(offset: int) -> str:
    head = (FILLER * (offset // len(FILLER) + 1))[:offset]
    return f'{head}var API_KEY="{KEY}";{FILLER}\n'


@pytest.mark.parametrize("offset", [100, 3000, 5000, 20000, 100000])
def test_credential_is_found_at_any_offset_on_a_minified_line(project: Path, offset: int) -> None:
    """The regression: a key past 4096 chars was previously invisible."""
    (project / "bundle.js").write_text(_bundle(offset), encoding="utf-8")
    findings = Scanner(Config()).scan(project).findings
    assert [f.rule_id for f in findings if f.rule_id == "AG001"] == ["AG001"], (
        f"credential at offset {offset} was not detected"
    )


def test_secret_rule_declares_unbounded_and_is_measured_linear() -> None:
    from agentguard.rules.secrets import HardcodedSecretRule

    assert HardcodedSecretRule.metadata.max_line_length == UNBOUNDED


def test_other_rules_stay_bounded(project: Path) -> None:
    """Only the measured-linear rule opts out; the default bound still applies elsewhere."""
    from agentguard.rules.code import DangerousExecutionRule

    assert DangerousExecutionRule.metadata.max_line_length is None
    (project / "b.js").write_text("x".ljust(DEFAULT_MAX_LINE_LENGTH + 500, "y") + "\n", encoding="utf-8")
    result = Scanner(Config()).scan(project)
    assert not result.fully_covered
    assert result.truncated[0].bound == DEFAULT_MAX_LINE_LENGTH


def test_coverage_is_reported_not_silent(project: Path) -> None:
    (project / "b.js").write_text("z" * 9000 + "\n", encoding="utf-8")
    result = Scanner(Config()).scan(project)

    assert result.truncated_lines == 1
    item = result.truncated[0]
    assert (item.line, item.length, item.bound) == (1, 9000, DEFAULT_MAX_LINE_LENGTH)
    assert item.to_dict(result.root)["withheld"] == 9000 - DEFAULT_MAX_LINE_LENGTH


def test_coverage_appears_in_every_report(project: Path) -> None:
    import json

    from agentguard.reporters import REPORTERS

    (project / "b.js").write_text("z" * 9000 + "\n", encoding="utf-8")
    result = Scanner(Config()).scan(project)

    payload = json.loads(REPORTERS["json"](result))
    assert payload["coverage"]["fully_covered"] is False
    assert payload["coverage"]["truncated_lines"][0]["withheld"] == 9000 - DEFAULT_MAX_LINE_LENGTH

    assert "Coverage" in REPORTERS["markdown"](result)

    sarif = json.loads(REPORTERS["sarif"](result))
    notes = sarif["runs"][0]["invocations"][0]["toolExecutionNotifications"]
    assert any("Coverage:" in n["message"]["text"] for n in notes)


def test_full_coverage_reports_clean(project: Path) -> None:
    (project / "a.py").write_text("value = 1\n", encoding="utf-8")
    result = Scanner(Config()).scan(project)
    assert result.fully_covered
    assert result.truncated == []


# --- the flag -------------------------------------------------------------------------


def test_truncation_does_not_gate_by_default(project: Path) -> None:
    (project / "b.js").write_text("z" * 9000 + "\n", encoding="utf-8")
    assert runner.invoke(app, ["scan", str(project)]).exit_code == 0


def test_fail_on_incomplete_gates(project: Path) -> None:
    (project / "b.js").write_text("z" * 9000 + "\n", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(project), "--fail-on-incomplete"])
    assert result.exit_code == 2
    assert "Coverage incomplete" in result.output


def test_fail_on_incomplete_passes_when_fully_covered(project: Path) -> None:
    (project / "a.py").write_text("value = 1\n", encoding="utf-8")
    assert runner.invoke(app, ["scan", str(project), "--fail-on-incomplete"]).exit_code == 0


# --- the declaration is enforced ------------------------------------------------------


def test_negative_bound_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_line_length"):
        RuleMetadata(
            "XX001",
            "t",
            Severity.LOW,
            "c",
            "d",
            languages=frozenset({"python"}),
            max_line_length=-1,
        )


class UnboundedRule(Rule):
    metadata = RuleMetadata(
        "XX901",
        "Unbounded",
        Severity.LOW,
        "test",
        "sees whole lines",
        languages=frozenset({"python"}),
        fixture_policy="report",
        max_line_length=UNBOUNDED,
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            if "NEEDLE" in line:
                yield self.finding(source, number, "found", "risk", "fix")


def test_a_rule_declaring_unbounded_sees_the_whole_line(project: Path) -> None:
    (project / "a.py").write_text("x" * 9000 + "NEEDLE\n", encoding="utf-8")
    result = Scanner(Config(), rules=[UnboundedRule()]).scan(project)
    assert [f.rule_id for f in result.findings] == ["XX901"]
