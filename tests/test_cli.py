from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agentguard.cli import app

runner = CliRunner()


def test_scan_clean_project(project: Path) -> None:
    (project / "clean.py").write_text("value = 1", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 0
    assert "No findings" in result.stdout


def test_scan_fails_threshold(project: Path) -> None:
    (project / "bad.py").write_text("os.system(user_input)", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 1


def test_json_output(project: Path) -> None:
    (project / "bad.py").write_text("os.system(user_input)", encoding="utf-8")
    output = project / "report.json"
    result = runner.invoke(
        app, ["scan", str(project), "--format", "json", "--output", str(output), "--fail-on", "none"]
    )
    assert result.exit_code == 0
    assert json.loads(output.read_text())["findings"]


def test_rules_command() -> None:
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == 0
    assert "AG001" in result.stdout


def test_init_config(project: Path) -> None:
    path = project / ".agentguard.yml"
    result = runner.invoke(app, ["init", "--path", str(path)])
    assert result.exit_code == 0
    assert path.exists()
    assert runner.invoke(app, ["init", "--path", str(path)]).exit_code == 2


def test_invalid_format(project: Path) -> None:
    result = runner.invoke(app, ["scan", str(project), "--format", "xml"])
    assert result.exit_code == 2


def test_version_matches_package_metadata() -> None:
    """Asserted against the metadata rather than a literal.

    A hardcoded version here would have to be edited in lockstep with `pyproject.toml`
    and `__init__.py`, which is the drift this test should be catching, not causing.
    """
    from importlib.metadata import version

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert version("agentguard-sast") in result.stdout
