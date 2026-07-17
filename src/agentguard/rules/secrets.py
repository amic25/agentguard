"""High-confidence secret detection."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from agentguard.context import SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules.base import Rule, RuleMetadata


class HardcodedSecretRule(Rule):
    metadata = RuleMetadata(
        "AG001",
        "Hardcoded secret",
        Severity.CRITICAL,
        "secrets",
        "Detects credentials committed to source files.",
    )
    _patterns = (
        ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
        ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
        ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
        ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
        ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        (
            "assigned credential",
            re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]([^'\"]{12,})['\"]"),
        ),
    )
    _placeholder = re.compile(r"(?i)(example|dummy|test|changeme|your[_-]|xxx|<|\$\{|process\.env)")

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            for kind, pattern in self._patterns:
                match = pattern.search(line)
                if not match:
                    continue
                value = match.group(1) if match.lastindex else match.group(0)
                if self._placeholder.search(value):
                    continue
                if kind == "assigned credential" and self._entropy(value) < 3.0:
                    continue
                yield self.finding(
                    source,
                    number,
                    f"A likely {kind} is embedded directly in source code.",
                    "Anyone with repository or build-artifact access may impersonate the service or access protected data.",
                    "Revoke and rotate the credential, remove it from history, and load the replacement from a secret manager or environment variable.",
                    column=match.start() + 1,
                )
                break

    @staticmethod
    def _entropy(value: str) -> float:
        if not value:
            return 0.0
        return -sum(
            (value.count(char) / len(value)) * math.log2(value.count(char) / len(value))
            for char in set(value)
        )
