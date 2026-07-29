"""High-confidence secret detection."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from agentguard.context import UNBOUNDED, SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules.base import Rule, RuleMetadata

#: Credentials that are published deliberately. A PostHog project key ships in client
#: JavaScript; a Stripe publishable key is printed in documentation; a Supabase anon key
#: is meant to reach the browser. Each is literally a committed credential, and reporting
#: one as a critical compromise is wrong — nothing is impersonated and nothing is
#: accessed. Measured as false positives in two of five real projects.
_PUBLIC_VALUE = re.compile(r"^(?:phc_[A-Za-z0-9]{20,}|pk_(?:live|test)_[A-Za-z0-9]{10,})$")
_PUBLIC_NAME = re.compile(r"(?i)(?:^|[^a-z])(?:public|publishable|anon|client[_-]?id)(?:[^a-z]|$)")


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
        # Runs over untruncated lines. A minified bundle with an inlined key is a real
        # and common leak, and it is exactly the shape that exceeds the default bound: a
        # key at offset 5,000 of a one-line bundle was previously missed entirely.
        # Permissible only because every pattern below is *measured* linear —
        # `python -m tools.measure_linearity` reports exponents of 0.98-1.01 and a
        # worst case of 42 ms on a 1 MB line. Re-run it before adding a pattern here.
        max_line_length=UNBOUNDED,
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
    #: Value shapes that are placeholders rather than credentials. `^\$` and `\$\{` both
    #: matter: `${VAR}` and a bare `$VAR` are references to a value held elsewhere, and a
    #: bare one was reported as a critical secret until a corpus case caught it. The
    #: `replace|insert|redacted` group covers template conventions that carry no marker
    #: word of their own - `sk-proj-replace-this-before-running` matched nothing before.
    _placeholder = re.compile(
        r"(?i)(example|dummy|test|changeme|your[_-]|xxx|<|\$\{|^\$|process\.env"
        r"|replace|placeholder|redacted|insert[_-]?your|todo|fixme)"
    )

    #: `.env` files conventionally leave values unquoted - `DB_PASSWORD=hunter2`, not
    #: `DB_PASSWORD="hunter2"` - so the quoted assigned-credential pattern misses the
    #: normal case entirely. Applied only to env files: requiring quotes is what keeps
    #: that pattern from matching `password = get_password()` in ordinary source.
    #:
    #: The name is captured whole and tested in Python rather than matched with
    #: `[A-Z0-9_]*KEYWORD[A-Z0-9_]*`. That form has two unbounded quantifiers around an
    #: alternation and measured quadratic - 918ms on 32KB, extrapolating to ~16 minutes
    #: on a 1MB line. AG001 runs unbounded, so that was a denial-of-service vector; the
    #: `--check` gate caught it before it shipped.
    _env_assignment = re.compile(r"^\s*(?:export\s+)?([A-Za-z0-9_]+)\s*=\s*(?!['\"])(\S{12,})\s*$")
    _env_credential_name = re.compile(r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd)")
    _env_file = re.compile(r"^\.env(?:\..+)?$")

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        env = bool(self._env_file.match(source.path.name))
        patterns = (
            (*self._patterns, ("environment credential", self._env_assignment)) if env else self._patterns
        )
        for number, line in enumerate(source.lines, 1):
            for kind, pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                if kind == "environment credential":
                    if not self._env_credential_name.search(match.group(1)):
                        continue
                    value, column = match.group(2), match.start(2) + 1
                else:
                    value = match.group(1) if match.lastindex else match.group(0)
                    column = (match.start(1) if match.lastindex else match.start()) + 1
                # `column` points at the credential, not the identifier before it. The
                # engine tests regions at this column, and `token: "contextvars.Token[Any]"`
                # is only distinguishable from a real credential by where the value sits.
                if self._placeholder.search(value):
                    continue
                if kind in {"assigned credential", "environment credential"} and self._entropy(value) < 3.0:
                    continue

                public = self._is_public(line[: match.start()], value)
                if public:
                    yield self.finding(
                        source,
                        number,
                        f"A likely {kind} is committed, but it is publishable by design.",
                        "Publishable keys are meant to be distributed, so exposure alone is not a "
                        "compromise. Confirm it is the publishable half and not the secret one, and "
                        "that no scope was granted to it beyond what public clients should have.",
                        "No rotation is required if this is genuinely the publishable key. If it is "
                        "not, treat it as a leaked secret and rotate.",
                        column=column,
                        confidence="medium",
                        metadata={"credential_class": "public", "kind": kind},
                    )
                else:
                    yield self.finding(
                        source,
                        number,
                        f"A likely {kind} is embedded directly in source code.",
                        "Anyone with repository or build-artifact access may impersonate the service or access protected data.",
                        "Revoke and rotate the credential, remove it from history, and load the replacement from a secret manager or environment variable.",
                        column=column,
                        metadata={"credential_class": "secret", "kind": kind},
                    )
                break

    @staticmethod
    def _is_public(prefix: str, value: str) -> bool:
        """Whether this is a key intended for publication.

        Judged from the value's own vendor prefix, or from the identifier it is assigned
        to. `SUPABASE_PUBLIC_API_KEY` says so in its name; a `phc_` value says so in its
        shape. Both were reported as critical compromises before this existed.
        """
        return bool(_PUBLIC_VALUE.match(value) or _PUBLIC_NAME.search(prefix))

    @staticmethod
    def _entropy(value: str) -> float:
        if not value:
            return 0.0
        return -sum(
            (value.count(char) / len(value)) * math.log2(value.count(char) / len(value))
            for char in set(value)
        )
