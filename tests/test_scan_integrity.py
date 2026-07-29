"""The scan-completeness invariant.

A scan may only report success when every enabled rule ran to completion over every
in-scope file. A rule that crashes, or a file that cannot be read, must never be
reported as a clean result.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard import scanner as scanner_module
from agentguard.cli import app
from agentguard.context import SourceFile
from agentguard.models import Finding, ScanResult, Severity
from agentguard.rules.base import Rule, RuleMetadata
from agentguard.scanner import Scanner

runner = CliRunner()


class ExplodingRule(Rule):
    """A rule that fails on every file, as a broken rule would after a bad refactor."""

    metadata = RuleMetadata(
        "XX999",
        "Exploding",
        Severity.LOW,
        "test",
        "always raises",
        languages=frozenset({"python", "manifest"}),
        fixture_policy="report",
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        raise RuntimeError("rule exploded")


def _result(errors: list[str]) -> ScanResult:
    return ScanResult(root=Path("/"), findings=[], files_scanned=1, rules_run=1, errors=errors)


def test_completed_is_false_when_errors_present() -> None:
    assert _result([]).completed is True
    assert _result(["AG001 failed on a.py: boom"]).completed is False


def test_scanner_records_rule_failure(project: Path) -> None:
    (project / "a.py").write_text("value = 1", encoding="utf-8")
    result = Scanner(rules=[ExplodingRule()]).scan(project)
    assert result.errors
    assert result.completed is False


def test_cli_exits_2_when_a_rule_crashes(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scanner_module, "BUILTIN_RULES", (ExplodingRule,))
    (project / "a.py").write_text("value = 1", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 2, "a rule failing on every file must not look like a clean scan"


def test_cli_exits_2_when_a_file_cannot_be_decoded(project: Path) -> None:
    (project / "broken.py").write_bytes(b"value = '\xff\xfe not utf-8'")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 2


def test_incomplete_scan_outranks_findings(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crashed scan is exit 2 even when findings were also produced: CI must be able to
    tell "found problems" from "the tool broke"."""
    monkeypatch.setattr(scanner_module, "BUILTIN_RULES", (*scanner_module.BUILTIN_RULES, ExplodingRule))
    (project / "bad.py").write_text("os.system(user_input)", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 2


def test_size_skip_is_policy_not_failure(project: Path) -> None:
    """Deliberate, declared skips are reported but do not make the scan incomplete."""
    (project / "big.py").write_text("value = 1\n" * 4000, encoding="utf-8")
    config = scanner_module.Config(max_file_size_kb=1)
    result = Scanner(config).scan(project)
    assert result.skipped_files == 1
    assert result.completed is True


def test_report_is_still_written_when_scan_is_incomplete(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial report is useful; the exit code carries the failure, not the absence of output."""
    monkeypatch.setattr(scanner_module, "BUILTIN_RULES", (ExplodingRule,))
    (project / "a.py").write_text("value = 1", encoding="utf-8")
    output = project / "report.json"
    result = runner.invoke(
        app, ["scan", str(project), "--format", "json", "--output", str(output), "--fail-on", "none"]
    )
    assert result.exit_code == 2
    assert json.loads(output.read_text(encoding="utf-8"))["scan"]["errors"]


def test_sarif_execution_successful_tracks_completed(project: Path) -> None:
    from agentguard.reporters import to_sarif

    (project / "a.py").write_text("value = 1", encoding="utf-8")
    result = Scanner(rules=[ExplodingRule()]).scan(project)
    payload = json.loads(to_sarif(result))
    assert payload["runs"][0]["invocations"][0]["executionSuccessful"] is result.completed is False
