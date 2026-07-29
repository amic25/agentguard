"""Rule authoring primitives.

A rule declares the context it applies to; it does not re-implement the checks. Language
gating, comment and docstring awareness, node-kind gating, and test-fixture handling were
each getting reinvented per rule, slightly differently and mostly wrong. They are now
fields on :class:`RuleMetadata`, enforced at construction, and applied centrally by the
scanner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from agentguard.context import KNOWN_LANGUAGES, SourceFile
from agentguard.models import Finding, Location, Severity
from agentguard.regions import REGION_NAMES

#: How a rule treats a match in a test, fixture, or example file. Live credentials do end
#: up in test fixtures, so the secret rules keep reporting there at reduced severity;
#: everything else is noise and is dropped.
FIXTURE_POLICIES = frozenset({"suppress", "downgrade", "report"})

#: Node kinds a rule may require the matched line to contain.
NODE_KINDS = frozenset({"call"})


@dataclass(frozen=True, slots=True)
class RuleMetadata:
    id: str
    title: str
    severity: Severity
    category: str
    description: str
    #: Languages this rule applies to. Required: a rule that does not say cannot be
    #: prevented from firing on a Dependabot manifest, which is how AG005 came to report
    #: `directory: "/"` as unrestricted filesystem access.
    languages: frozenset[str] = field(default=frozenset())
    #: Regions a match is meaningless inside. Defaults exclude comments and docstrings,
    #: because documentation showing a credential is not a committed credential.
    ignore_regions: frozenset[str] = frozenset({"comment", "docstring"})
    #: If set, the matched line must contain one of these node kinds. `{"call"}` is what
    #: separates `transfer_funds(x)` from `def transfer_funds(x)`.
    require_nodes: frozenset[str] = frozenset()
    #: Behaviour in test, fixture, example, and vendored files.
    fixture_policy: str = "suppress"
    #: Longest line this rule is handed. ``None`` inherits the scanner's configured
    #: bound. ``UNBOUNDED`` (0) opts out of truncation entirely and is only permissible
    #: for patterns *measured* linear — an unbounded non-linear pattern is a
    #: denial-of-service vector. Record the measurement when setting it.
    max_line_length: int | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.title:
            raise ValueError("rule metadata requires an id and a title")
        if not self.languages:
            raise ValueError(
                f"{self.id}: `languages` must be declared. A rule that does not say which "
                f"languages it applies to will be run against every file type, including "
                f"CI configuration and lockfiles."
            )
        unknown = set(self.languages) - KNOWN_LANGUAGES
        if unknown:
            raise ValueError(f"{self.id}: unknown languages: {', '.join(sorted(unknown))}")
        unknown = set(self.ignore_regions) - REGION_NAMES
        if unknown:
            raise ValueError(f"{self.id}: unknown regions: {', '.join(sorted(unknown))}")
        unknown = set(self.require_nodes) - NODE_KINDS
        if unknown:
            raise ValueError(f"{self.id}: unknown node kinds: {', '.join(sorted(unknown))}")
        if self.fixture_policy not in FIXTURE_POLICIES:
            raise ValueError(
                f"{self.id}: fixture_policy must be one of {', '.join(sorted(FIXTURE_POLICIES))}"
            )
        if self.max_line_length is not None and self.max_line_length < 0:
            raise ValueError(f"{self.id}: max_line_length must be >= 0 (0 means unbounded)")

    def applies_to(self, source: SourceFile) -> bool:
        return source.language in self.languages


class Rule(ABC):
    """Base class for built-in and third-party security rules."""

    metadata: RuleMetadata

    @abstractmethod
    def scan(self, source: SourceFile) -> Iterable[Finding]:
        """Return findings for a single file."""

    def finding(
        self,
        source: SourceFile,
        line: int,
        explanation: str,
        risk: str,
        remediation: str,
        *,
        column: int = 1,
        confidence: str = "high",
        references: tuple[str, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> Finding:
        return Finding(
            rule_id=self.metadata.id,
            title=self.metadata.title,
            severity=self.metadata.severity,
            location=Location(source.path, line, column),
            explanation=explanation,
            risk=risk,
            remediation=remediation,
            category=self.metadata.category,
            confidence=confidence,
            references=references,
            metadata=metadata or {},
        )
