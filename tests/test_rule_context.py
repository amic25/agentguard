"""Rules declare their context; the engine enforces it.

Language gating, comment and docstring awareness, node-kind gating, and fixture handling
used to be re-derived inside each rule, slightly differently and mostly wrong. These
tests pin the declarations and the central enforcement, so a rule added later inherits
the behaviour instead of reinventing it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from agentguard.config import Config
from agentguard.context import SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules import BUILTIN_RULES
from agentguard.rules.base import Rule, RuleMetadata
from agentguard.scanner import Scanner


def _findings(project: Path, name: str, content: str) -> list[Finding]:
    (project / name).write_text(content, encoding="utf-8")
    return Scanner(Config()).scan(project).findings


def _rules(findings: list[Finding]) -> set[str]:
    return {finding.rule_id for finding in findings}


# --- the schema is enforced, not documented -------------------------------------------


def test_metadata_requires_declared_languages() -> None:
    with pytest.raises(ValueError, match="languages"):
        RuleMetadata("XX001", "t", Severity.LOW, "c", "d")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"languages": frozenset({"cobol"})}, "unknown languages"),
        ({"languages": frozenset({"python"}), "ignore_regions": frozenset({"nope"})}, "unknown regions"),
        ({"languages": frozenset({"python"}), "require_nodes": frozenset({"nope"})}, "unknown node kinds"),
        ({"languages": frozenset({"python"}), "fixture_policy": "maybe"}, "fixture_policy"),
    ],
)
def test_metadata_rejects_undeclarable_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RuleMetadata("XX001", "t", Severity.LOW, "c", "d", **kwargs)  # type: ignore[arg-type]


def test_every_builtin_rule_declares_its_languages() -> None:
    for kind in BUILTIN_RULES:
        assert kind.metadata.languages, f"{kind.metadata.id} declares no languages"


# --- language gating -------------------------------------------------------------------


def test_filesystem_rule_does_not_read_ci_configuration(project: Path) -> None:
    """`directory: "/"` in a Dependabot manifest is not filesystem access."""
    found = _findings(project, "dependabot.yml", 'version: 2\nupdates:\n  - directory: "/"\n')
    assert "AG005" not in _rules(found)


def test_dependency_rule_only_reads_manifests(project: Path) -> None:
    found = _findings(project, "app.py", "requests\n")
    assert "AG010" not in _rules(found)


# --- comment, docstring, and annotation regions ---------------------------------------


def test_secret_in_a_docstring_is_not_a_committed_secret(project: Path) -> None:
    content = '''"""Example.

    >>> connect(password="s3cr3t-Kq2ZmVx9Lp4Rt")
    """
'''
    assert "AG001" not in _rules(_findings(project, "mod.py", content))


def test_secret_in_a_comment_is_not_a_committed_secret(project: Path) -> None:
    content = '# historical: password = "s3cr3t-Kq2ZmVx9Lp4Rt"\nvalue = 1\n'
    assert "AG001" not in _rules(_findings(project, "mod.py", content))


def test_type_annotation_is_not_a_credential(project: Path) -> None:
    content = (
        'import contextvars\n\n\ndef reset(token: "contextvars.Token[object]") -> None:\n    return None\n'
    )
    assert "AG001" not in _rules(_findings(project, "mod.py", content))


def test_a_real_assignment_is_still_reported(project: Path) -> None:
    """The regions must not swallow the case the rule exists for."""
    content = 'DATABASE_PASSWORD = "b7Kq2ZmVx9Lp4Rt6Wn3Jc"\n'
    assert "AG001" in _rules(_findings(project, "mod.py", content))


def test_javascript_comments_are_regions_too(project: Path) -> None:
    content = "// tool({ name: 'x' })\nconst a = 1;\n"
    assert "AG007" not in _rules(_findings(project, "app.js", content))


# --- node-kind gating ------------------------------------------------------------------


def test_defining_a_high_impact_function_is_not_performing_it(project: Path) -> None:
    content = "def delete_file(path: str) -> bool:\n    return True\n\n\ndef deploy(env: str) -> None:\n    return None\n"
    assert "AG008" not in _rules(_findings(project, "mod.py", content))


def test_calling_a_high_impact_function_is_still_reported(project: Path) -> None:
    content = "def handle(amount: int) -> None:\n    transfer_funds(amount)\n"
    assert "AG008" in _rules(_findings(project, "mod.py", content))


def test_method_named_exec_is_not_the_builtin(project: Path) -> None:
    content = "class S:\n    async def run(self, *cmd):\n        return await super().exec(*cmd)\n"
    assert "AG002" not in _rules(_findings(project, "mod.py", content))


def test_eval_on_a_literal_has_no_untrusted_input(project: Path) -> None:
    assert "AG002" not in _rules(_findings(project, "mod.py", "SETTINGS = eval(\"{'a': 1}\")\n"))


def test_eval_on_a_variable_is_still_reported(project: Path) -> None:
    content = "def run(expression: str) -> object:\n    return eval(expression)\n"
    assert "AG002" in _rules(_findings(project, "mod.py", content))


# --- fixture paths ---------------------------------------------------------------------


def test_fixture_path_is_recognised(project: Path) -> None:
    root = project
    for relative in ("tests/test_x.py", "examples/demo.py", "docs/sample.py", "src/conftest.py"):
        path = root / relative
        source = SourceFile(path, root, "", "python")
        assert source.is_fixture, f"{relative} should be treated as a fixture path"
    assert not SourceFile(root / "src/agent.py", root, "", "python").is_fixture


def test_secrets_are_downgraded_in_fixtures_not_silenced(project: Path) -> None:
    """Credentials really do get committed to test fixtures."""
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_client.py").write_text(
        'def test_auth():\n    client = build(api_key="b7Kq2ZmVx9Lp4Rt6Wn3Jc")\n', encoding="utf-8"
    )
    findings = Scanner(Config()).scan(project).findings
    secrets = [finding for finding in findings if finding.rule_id == "AG001"]
    assert secrets, "a credential in a fixture must still be reported"
    assert secrets[0].severity <= Severity.MEDIUM, (
        "must land below the default --fail-on high gate, or fixtures still block CI"
    )
    assert secrets[0].confidence == "low"
    assert secrets[0].metadata.get("fixture_path") is True


def test_non_secret_rules_are_suppressed_in_fixtures(project: Path) -> None:
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_exec.py").write_text(
        "def test_run(cmd):\n    import os\n    os.system(cmd)\n", encoding="utf-8"
    )
    assert "AG002" not in _rules(Scanner(Config()).scan(project).findings)


def test_production_code_is_unaffected_by_fixture_policy(project: Path) -> None:
    src = project / "src"
    src.mkdir()
    (src / "agent.py").write_text("def run(cmd):\n    import os\n    os.system(cmd)\n", encoding="utf-8")
    findings = Scanner(Config()).scan(project).findings
    assert "AG002" in _rules(findings)
    assert next(f for f in findings if f.rule_id == "AG002").severity == Severity.CRITICAL


# --- a rule cannot opt out of the engine ------------------------------------------------


class LoudRule(Rule):
    metadata = RuleMetadata(
        "XX900",
        "Loud",
        Severity.HIGH,
        "test",
        "fires on every line",
        languages=frozenset({"python"}),
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, _ in enumerate(source.lines, 1):
            yield self.finding(source, number, "e", "r", "fix")


def test_engine_gates_apply_to_third_party_rules(project: Path) -> None:
    """A plugin inherits comment awareness and fixture policy without asking."""
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_a.py").write_text("value = 1\n", encoding="utf-8")
    result = Scanner(Config(), rules=[LoudRule()]).scan(project)
    assert not result.findings, "default fixture_policy=suppress must apply to plugins too"


def test_scanning_a_test_directory_directly_still_classifies_it(project: Path) -> None:
    """`agentguard scan tests/` must not read a whole suite as production code.

    Classifying only on the path below the scan root meant pointing the scanner at a
    fixture directory silently disabled the fixture policy, which is exactly when it is
    most needed. Caught by SARIF alerts rendering a corpus fixture as `critical`.
    """
    tests_dir = project / "tests"
    tests_dir.mkdir()
    # deliberately NOT named test_*, so only the path can classify it
    (tests_dir / "helpers.py").write_text('api_key = "b7Kq2ZmVx9Lp4Rt6Wn3Jc"\n', encoding="utf-8")

    from_parent = Scanner(Config()).scan(project).findings
    from_inside = Scanner(Config()).scan(tests_dir).findings

    assert [f.severity for f in from_parent] == [Severity.MEDIUM]
    assert [f.severity for f in from_inside] == [Severity.MEDIUM], (
        "scanning the fixture directory directly must classify it the same way"
    )


def test_a_checkout_under_a_directory_named_test_is_not_all_fixtures(project: Path) -> None:
    """Only the scan root's own name is added, never the absolute path above it."""
    root = project / "test" / "myproject"
    (root / "src").mkdir(parents=True)
    (root / "src" / "agent.py").write_text('api_key = "b7Kq2ZmVx9Lp4Rt6Wn3Jc"\n', encoding="utf-8")
    findings = Scanner(Config()).scan(root).findings
    assert [f.severity for f in findings] == [Severity.CRITICAL]
