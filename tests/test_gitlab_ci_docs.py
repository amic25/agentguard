from __future__ import annotations

from pathlib import Path

import yaml


def test_gitlab_ci_example() -> None:
    example = Path("docs/integrations/gitlab-ci.yml")
    config = yaml.safe_load(example.read_text(encoding="utf-8"))
    job = config["agentguard"]

    assert job["stage"] == "security"
    assert job["script"] == ["agentguard scan . --format json --output agentguard-report.json --fail-on high"]
    assert job["artifacts"]["when"] == "always"
    assert "agentguard-report.json" in job["artifacts"]["paths"]
