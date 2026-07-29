"""Stable data model shared by rules, reporters, and plugins."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any


class Severity(IntEnum):
    """Finding priority; larger values are more severe."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, value: str) -> Severity:
        try:
            return cls[value.upper()]
        except KeyError as exc:
            choices = ", ".join(item.name.lower() for item in cls)
            raise ValueError(f"severity must be one of: {choices}") from exc


@dataclass(frozen=True, slots=True)
class Location:
    """One source location."""

    path: Path
    line: int = 1
    column: int = 1


@dataclass(frozen=True, slots=True)
class Finding:
    """A normalized security finding emitted by a rule."""

    rule_id: str
    title: str
    severity: Severity
    location: Location
    explanation: str
    risk: str
    remediation: str
    category: str
    confidence: str = "high"
    references: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, root: Path | None = None) -> dict[str, Any]:
        data = asdict(self)
        path = self.location.path
        if root:
            with suppress(ValueError):
                path = path.relative_to(root)
        data["severity"] = self.severity.name.title()
        data["location"]["path"] = path.as_posix()
        data["references"] = list(self.references)
        return data


@dataclass(frozen=True, slots=True)
class TruncatedLine:
    """A line some rule was not shown in full, and by how much."""

    path: Path
    line: int
    length: int
    bound: int

    def to_dict(self, root: Path | None = None) -> dict[str, Any]:
        path = self.path
        if root:
            with suppress(ValueError):
                path = path.relative_to(root)
        return {
            "path": path.as_posix(),
            "line": self.line,
            "length": self.length,
            "bound": self.bound,
            "withheld": self.length - self.bound,
        }


@dataclass(slots=True)
class ScanResult:
    """Aggregate result of one scan."""

    root: Path
    findings: list[Finding]
    files_scanned: int
    rules_run: int
    skipped_files: int = 0
    truncated: list[TruncatedLine] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def truncated_lines(self) -> int:
        """Count of lines withheld in full from at least one rule."""
        return len(self.truncated)

    @property
    def fully_covered(self) -> bool:
        """True when every rule saw every in-scope line in full.

        Distinct from :attr:`completed`. A scan can finish cleanly and still not have
        looked at everything, which is why truncation is reported rather than silently
        folded into success.
        """
        return not self.truncated

    @property
    def completed(self) -> bool:
        """True when every enabled rule ran to completion over every in-scope file.

        This is the scan-integrity invariant: a caller may only treat a result as
        trustworthy when it holds. A rule that raised, or a file that could not be read,
        means some code went unexamined, and an unexamined file is not a clean file.

        Files skipped by declared policy (``max_file_size_kb``) are deliberate and
        reported via :attr:`skipped_files`; they are not failures and do not clear
        this flag.
        """
        return not self.errors

    def counts(self) -> dict[str, int]:
        return {
            severity.name.title(): sum(finding.severity == severity for finding in self.findings)
            for severity in reversed(Severity)
        }
