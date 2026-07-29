"""Project discovery and rule orchestration."""

from __future__ import annotations

import fnmatch
import time
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path

from agentguard.config import Config
from agentguard.context import SourceFile
from agentguard.models import Finding, ScanResult, Severity
from agentguard.plugins import load_plugins
from agentguard.rules import BUILTIN_RULES, Rule

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "manifest",
    ".txt": "manifest",
    ".toml": "manifest",
    ".yaml": "manifest",
    ".yml": "manifest",
}
SPECIAL_FILES = {"Dockerfile", "Pipfile", "package-lock.json", "requirements.txt"}


class Scanner:
    """Scan a directory with built-in and custom rules."""

    def __init__(self, config: Config | None = None, rules: Sequence[Rule] | None = None):
        self.config = config or Config()
        candidates = list(rules) if rules is not None else [kind() for kind in BUILTIN_RULES]
        candidates.extend(load_plugins(self.config.plugin_modules))
        ids = [rule.metadata.id for rule in candidates]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate rule IDs: {', '.join(duplicates)}")
        self.rules = [rule for rule in candidates if rule.metadata.id not in self.config.disabled_rules]

    def scan(self, target: Path | str) -> ScanResult:
        started = time.perf_counter()
        target_path = Path(target).expanduser().resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"scan target does not exist: {target_path}")
        root = target_path if target_path.is_dir() else target_path.parent
        findings: list[Finding] = []
        errors: list[str] = []
        scanned = 0
        skipped = 0
        truncated = 0
        for path in self._files(target_path, root):
            try:
                if path.stat().st_size > self.config.max_file_size_kb * 1024:
                    skipped += 1
                    continue
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{path}: {exc}")
                skipped += 1
                continue
            scanned += 1
            source = SourceFile(
                path,
                root,
                content,
                LANGUAGES.get(path.suffix.lower(), "manifest"),
                max_line_length=self.config.max_line_length,
            )
            for rule in self.rules:
                try:
                    for finding in rule.scan(source):
                        if self._suppressed(source, finding):
                            continue
                        severity = self.config.severity_overrides.get(finding.rule_id)
                        findings.append(
                            replace(finding, severity=Severity.parse(severity)) if severity else finding
                        )
                except Exception as exc:
                    errors.append(f"{rule.metadata.id} failed on {source.relative_path}: {exc}")
            truncated += source.truncated_lines
        findings.sort(
            key=lambda item: (
                -int(item.severity),
                item.location.path.as_posix(),
                item.location.line,
                item.rule_id,
            )
        )
        return ScanResult(
            root=root,
            findings=findings,
            files_scanned=scanned,
            rules_run=len(self.rules),
            skipped_files=skipped,
            truncated_lines=truncated,
            errors=errors,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    def _files(self, target: Path, root: Path) -> Iterable[Path]:
        candidates = [target] if target.is_file() else target.rglob("*")
        for path in candidates:
            if not path.is_file() or (path.is_symlink() and not self.config.follow_symlinks):
                continue
            relative = path.relative_to(root).as_posix()
            if self._excluded(relative):
                continue
            if (
                path.suffix.lower() in LANGUAGES
                or path.name in SPECIAL_FILES
                or path.name.startswith("requirements")
            ):
                yield path

    def _excluded(self, path: str) -> bool:
        return any(
            fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(f"{path}/", pattern)
            for pattern in self.config.exclude
        )

    @staticmethod
    def _suppressed(source: SourceFile, finding: Finding) -> bool:
        lines = source.lines
        index = max(0, finding.location.line - 1)
        nearby = lines[max(0, index - 1) : index + 1]
        return any(
            "agentguard: ignore" in line
            and (f"[{finding.rule_id}]" in line or "agentguard: ignore\n" in f"{line}\n")
            for line in nearby
        )
