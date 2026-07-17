from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.config import Config
from agentguard.models import Severity
from agentguard.scanner import Scanner


@pytest.mark.parametrize(
    ("filename", "content", "rule_id"),
    [
        ("agent.py", 'OPENAI_API_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"', "AG001"),
        ("agent.py", 'GOOGLE_API_KEY = "AIzaSyB3X_97fX7Z-2kLmNpQrStUvWxYz123456"', "AG001"),
        ("agent.py", "import os\nos.system(user_input)", "AG002"),
        ("agent.py", "Agent(tools=[shell, browser])", "AG003"),
        ("agent.py", 'prompt = f"Summarize: {user_input}"', "AG004"),
        ("agent.py", "open(user_path).read()", "AG005"),
        ("agent.py", 'requests.get("http://insecure.example/api")', "AG006"),
        ("agent.py", "@tool\ndef lookup(value):\n    return value", "AG007"),
        ("agent.py", "def act():\n    transfer_funds(amount)", "AG008"),
        ("requirements.txt", "langchain==0.1.0", "AG009"),
        ("requirements.txt", "langchain", "AG010"),
        ("agent.ts", "execSync(command)", "AG002"),
        ("agent.ts", "const prompt = `Read ${web_content}`", "AG004"),
        ("agent.ts", "fetch(url)", "AG006"),
        ("agent.ts", "tool({ name: 'lookup', execute: run })", "AG007"),
    ],
)
def test_detects_each_rule(project: Path, filename: str, content: str, rule_id: str) -> None:
    (project / filename).write_text(content, encoding="utf-8")
    result = Scanner().scan(project)
    assert rule_id in {finding.rule_id for finding in result.findings}


def test_safe_code_has_no_findings(project: Path) -> None:
    (project / "agent.py").write_text(
        "from pathlib import Path\n"
        "SANDBOX = Path('/srv/sandbox')\n"
        "def summarize(text: str) -> str:\n"
        "    return text[:1000]\n",
        encoding="utf-8",
    )
    assert Scanner().scan(project).findings == []


def test_placeholder_secret_is_ignored(project: Path) -> None:
    (project / "settings.py").write_text('api_key = "your_api_key_here"', encoding="utf-8")
    assert Scanner().scan(project).findings == []


def test_google_api_key_placeholder_is_ignored(project: Path) -> None:
    (project / "settings.py").write_text(
        'GOOGLE_API_KEY = "AIzaSyYOUR_API_KEY_HERE1234567890123456"', encoding="utf-8"
    )
    assert Scanner().scan(project).findings == []


def test_rule_suppression(project: Path) -> None:
    (project / "agent.py").write_text(
        "# agentguard: ignore[AG002]\nos.system(trusted_constant)", encoding="utf-8"
    )
    assert Scanner().scan(project).findings == []


def test_severity_override(project: Path) -> None:
    (project / "requirements.txt").write_text("requests", encoding="utf-8")
    result = Scanner(Config(severity_overrides={"AG010": "medium"})).scan(project)
    assert result.findings[0].severity is Severity.MEDIUM


def test_excludes_vendor_directory(project: Path) -> None:
    vendor = project / "node_modules"
    vendor.mkdir()
    (vendor / "bad.js").write_text("execSync(command)", encoding="utf-8")
    result = Scanner().scan(project)
    assert result.files_scanned == 0


def test_skips_oversized_files(project: Path) -> None:
    (project / "large.py").write_text("x" * 2000, encoding="utf-8")
    result = Scanner(Config(max_file_size_kb=1)).scan(project)
    assert result.skipped_files == 1


def test_missing_target_raises(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Scanner().scan(project / "missing")


@pytest.mark.parametrize(
    ("dependency", "version", "detected"),
    [
        ("axios", "1.3.1", False),
        ("axios", "1.7.2", True),
        ("axios", "1.7.4", False),
        ("langchain-community", "0.0.27", True),
        ("langchain-community", "0.0.28", False),
        ("openai", "1.0.0", False),
    ],
)
def test_advisory_boundaries(project: Path, dependency: str, version: str, detected: bool) -> None:
    (project / "package.json").write_text(
        f'{{"dependencies": {{"{dependency}": "{version}"}}}}', encoding="utf-8"
    )
    result = Scanner().scan(project)
    assert ("AG009" in {finding.rule_id for finding in result.findings}) is detected
