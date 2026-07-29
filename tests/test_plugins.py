from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.config import Config
from agentguard.plugins import PluginError
from agentguard.scanner import Scanner


def test_module_plugin(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / "my_rules.py").write_text(
        "from agentguard.rules import Rule, RuleMetadata\n"
        "from agentguard.models import Severity\n"
        "class Custom(Rule):\n"
        "    metadata = RuleMetadata('CUSTOM001', 'Custom risk', Severity.LOW, 'custom', 'Demo',\n"
        "                            languages=frozenset({'python'}), fixture_policy='report')\n"
        "    def scan(self, source):\n"
        "        if 'custom_bad' in source.content:\n"
        "            yield self.finding(source, 1, 'Found custom bad.', 'Custom risk.', 'Remove it.')\n"
        "rules = [Custom]\n",
        encoding="utf-8",
    )
    (project / "sample.py").write_text("custom_bad = True", encoding="utf-8")
    monkeypatch.syspath_prepend(str(project))
    result = Scanner(Config(plugin_modules=["my_rules"])).scan(project)
    assert "CUSTOM001" in {item.rule_id for item in result.findings}


def test_invalid_plugin(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / "broken_plugin.py").write_text("value = 1", encoding="utf-8")
    monkeypatch.syspath_prepend(str(project))
    with pytest.raises(PluginError):
        Scanner(Config(plugin_modules=["broken_plugin"]))
