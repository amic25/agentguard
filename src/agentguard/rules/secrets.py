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
        languages=frozenset({"python", "javascript", "typescript", "manifest"}),
        # Ordinary string literals are exactly where credentials live, so `string` is not
        # ignored. Docstrings and comments are documentation, and `annotation` keeps a
        # type like `token: "contextvars.Token[Any]"` from reading as a credential.
        ignore_regions=frozenset({"comment", "docstring", "annotation"}),
        # Live credentials really do get committed to fixtures, so these are reported at
        # reduced severity rather than dropped.
        fixture_policy="downgrade",
    )
    _patterns = (
        ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
        ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
        ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
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
                # Point at the credential, not at the identifier before it. The engine
                # tests regions at this column, and `token: "contextvars.Token[Any]"` is
                # only distinguishable from a real credential by where the value sits.
                column = (match.start(1) if match.lastindex else match.start()) + 1
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
                    column=column,
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
