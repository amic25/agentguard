"""No output path may reproduce the credential it matched.

AgentGuard reports are routinely uploaded somewhere less private than the repository:
SARIF goes to GitHub code scanning, JSON and Markdown become CI artifacts, and terminal
output lands in build logs. Echoing a matched credential into any of those turns a
finding into a second disclosure.

Today this holds structurally, because ``Finding`` has no field capable of carrying a
snippet. That is a property of the current design and not a guarantee — the first
"show me the offending line" feature request would end it. These tests assert the
behaviour directly, and iterate over the reporter registry so that a newly added
reporter is covered the moment it is registered rather than whenever someone remembers.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from agentguard.config import Config
from agentguard.models import ScanResult
from agentguard.reporters import REPORTERS, render_terminal
from agentguard.scanner import Scanner

#: Values that must never be echoed. Chosen to match the AG001 patterns and to be
#: distinctive enough that a substring hit is unambiguous.
SECRETS = {
    "openai": "sk-proj-Xk92LmQp4RtVzYwB7NcJdHsG3FaEuT6i",
    "aws": "AKIAZQ3RN7WXKLPD2VUH",
    "github": "ghp_9KdLmQ2wXtYbN4vRfP7zHjC5sA1eGu3TiOpZ",
    "assigned": "hunter2-J8kLmQ4wXtYbN9vRfP7z",
}


@pytest.fixture
def scanned(project: Path) -> ScanResult:
    project.joinpath("creds.py").write_text(
        "\n".join(
            [
                f'OPENAI_API_KEY = "{SECRETS["openai"]}"',
                f'AWS_ACCESS_KEY_ID = "{SECRETS["aws"]}"',
                f'GITHUB_TOKEN = "{SECRETS["github"]}"',
                f'db_password = "{SECRETS["assigned"]}"',
            ]
        ),
        encoding="utf-8",
    )
    result = Scanner(Config()).scan(project)
    # Guard against a vacuous test: if nothing matched, the assertions below prove nothing.
    assert result.findings, "fixture must actually trigger the secret rule"
    return result


def _assert_no_secret_in(text: str, label: str) -> None:
    for name, value in SECRETS.items():
        assert value not in text, f"{label} disclosed the {name} credential"


@pytest.mark.parametrize("name", sorted(REPORTERS))
def test_registered_reporters_do_not_disclose_secrets(name: str, scanned: ScanResult) -> None:
    _assert_no_secret_in(REPORTERS[name](scanned), f"the {name} reporter")


def test_terminal_output_does_not_disclose_secrets(scanned: ScanResult) -> None:
    buffer = io.StringIO()
    # width set wide so nothing is hidden by truncation rather than by design
    render_terminal(scanned, Console(file=buffer, width=400, no_color=True))
    _assert_no_secret_in(buffer.getvalue(), "terminal output")


def test_finding_fields_do_not_disclose_secrets(scanned: ScanResult) -> None:
    """Covers any reporter, present or future, that serialises a Finding wholesale."""
    for finding in scanned.findings:
        _assert_no_secret_in(repr(finding.to_dict(scanned.root)), "Finding.to_dict")
        _assert_no_secret_in(repr(finding), "Finding repr")


def test_scan_warnings_do_not_disclose_secrets(project: Path) -> None:
    """``result.errors`` reaches JSON, Markdown, SARIF notifications, and the terminal.

    Nothing in the scanner or the built-in rules may put matched text into that channel.
    (The scanner passes a rule's exception text through verbatim, so a *plugin* rule that
    quotes a secret in an exception would disclose it. That is documented as a plugin
    authoring constraint in docs/PLUGINS.md rather than defended against here.)
    """
    project.joinpath("creds.py").write_text(f'KEY = "{SECRETS["openai"]}"\n', encoding="utf-8")
    project.joinpath("broken.py").write_bytes(f'KEY = "{SECRETS["github"]}" # \xff\xfe'.encode("latin-1"))
    result = Scanner(Config()).scan(project)

    assert result.errors, "fixture must actually exercise the error path"
    for error in result.errors:
        _assert_no_secret_in(error, "a scan warning")
    for name, render in REPORTERS.items():
        _assert_no_secret_in(render(result), f"the {name} reporter (warnings included)")


def test_source_content_never_reaches_a_reporter(scanned: ScanResult) -> None:
    """The structural property, asserted rather than assumed: no Finding field is large
    enough to be carrying source text."""
    for finding in scanned.findings:
        for key, value in finding.to_dict(scanned.root).items():
            if isinstance(value, str):
                assert "\n" not in value, f"{key} carries multi-line text, which may be source"
