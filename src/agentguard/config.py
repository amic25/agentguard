"""Configuration loading, and the trust boundary between operator and repository.

AgentGuard scans untrusted code. The repository under scan may therefore contain a
hostile ``.agentguard.yml``, and that file must not be able to weaken the scan or reach
the scanner process. Two distinct types carry that boundary:

``RepoConfig``
    Parsed from the scanned repository. Untrusted. Cannot express a setting that would
    weaken a scan, because no such field exists on the type.

``Config``
    The effective, operator-controlled configuration. Trusted. Reached only via an
    explicit ``--config`` path, which is the operator's act of vouching for the file.

``Config.tightened_by`` is the only route from one to the other, and it is monotone: it
may narrow scope or raise strictness, never the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentguard.context import DEFAULT_MAX_LINE_LENGTH

DEFAULT_EXCLUDES = (
    ".git/**",
    ".venv/**",
    "venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "coverage/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
)

#: Settings a scanned repository may supply. Every key here must have an unambiguous
#: "safer" direction that :meth:`Config.tightened_by` can enforce. Adding a key widens
#: the untrusted attack surface and requires the same justification.
REPO_KEYS = frozenset({"exclude", "max_file_size_kb", "max_line_length", "follow_symlinks"})

#: Settings only an operator may supply, and the reason each is withheld. These are the
#: settings a hostile repository would want: they weaken detection or execute code.
OPERATOR_ONLY_KEYS: dict[str, str] = {
    "plugins": "imports and executes arbitrary Python inside the scanner process",
    "disabled_rules": "switches rules off, lowering strictness",
    "severity_overrides": "can lower a finding below the --fail-on threshold",
}


class UntrustedConfigError(ValueError):
    """A scanned repository's config tried to set something only an operator may set."""


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: configuration must be a mapping")
    return raw


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


@dataclass(frozen=True, slots=True)
class RepoConfig:
    """Settings taken from the scanned repository's ``.agentguard.yml``. Untrusted.

    This type deliberately has no ``plugins`` field, and no field whose value could make
    a scan weaker. The boundary is held by the shape of the type rather than by a check
    that a later refactor could quietly drop: a setting that cannot be represented here
    cannot cross into the scanner at all.

    Every field is optional. ``None`` means "the repository said nothing", which is
    distinct from a repository explicitly restating the operator's value.
    """

    exclude: tuple[str, ...] = ()
    max_file_size_kb: int | None = None
    max_line_length: int | None = None
    follow_symlinks: bool | None = None

    @classmethod
    def discover(cls, root: Path) -> RepoConfig:
        """Read ``root/.agentguard.yml`` if present, rejecting operator-only settings."""
        candidate = root / ".agentguard.yml"
        if not candidate.exists():
            return cls()
        return cls.parse(candidate)

    @classmethod
    def parse(cls, path: Path) -> RepoConfig:
        raw = _load_mapping(path)
        for key, reason in OPERATOR_ONLY_KEYS.items():
            if key in raw:
                raise UntrustedConfigError(
                    f"{path}: '{key}' cannot be set by a scanned repository because it {reason}. "
                    f"AgentGuard treats the scanned repository as untrusted input. If this file is "
                    f"yours and you intend it, vouch for it explicitly with "
                    f"--config {path.name}."
                )
        unknown = set(raw) - REPO_KEYS
        if unknown:
            raise ValueError(f"{path}: unknown keys: {', '.join(sorted(unknown))}")
        size = raw.get("max_file_size_kb")
        line = raw.get("max_line_length")
        follow = raw.get("follow_symlinks")
        return cls(
            exclude=tuple(_strings(raw.get("exclude", []), "exclude")),
            max_file_size_kb=None if size is None else _positive_int(size, "max_file_size_kb"),
            max_line_length=None if line is None else _positive_int(line, "max_line_length"),
            follow_symlinks=None if follow is None else _bool(follow, "follow_symlinks"),
        )


@dataclass(slots=True)
class Config:
    """Effective scanner configuration. Operator-controlled and trusted."""

    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    disabled_rules: set[str] = field(default_factory=set)
    severity_overrides: dict[str, str] = field(default_factory=dict)
    plugin_modules: list[str] = field(default_factory=list)
    max_file_size_kb: int = 1024
    max_line_length: int = DEFAULT_MAX_LINE_LENGTH
    follow_symlinks: bool = False

    @classmethod
    def load(cls, path: Path | None, root: Path) -> Config:
        """Build the effective configuration.

        An explicit ``path`` is the operator vouching for that file, so it is parsed with
        the full schema. With no explicit path, the scanned repository's own
        ``.agentguard.yml`` is discovered and may only tighten the defaults.
        """
        if path is not None:
            return cls.operator(path)
        return cls().tightened_by(RepoConfig.discover(root))

    @classmethod
    def operator(cls, path: Path) -> Config:
        """Parse a config the operator has explicitly vouched for. Full schema."""
        if not path.exists():
            raise ValueError(f"config file does not exist: {path}")
        raw = _load_mapping(path)
        allowed = REPO_KEYS | set(OPERATOR_ONLY_KEYS)
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"{path}: unknown keys: {', '.join(sorted(unknown))}")
        overrides = raw.get("severity_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("severity_overrides must be a mapping")
        defaults = cls()
        size = raw.get("max_file_size_kb")
        line = raw.get("max_line_length")
        follow = raw.get("follow_symlinks")
        return cls(
            exclude=[*defaults.exclude, *_strings(raw.get("exclude", []), "exclude")],
            disabled_rules=set(_strings(raw.get("disabled_rules", []), "disabled_rules")),
            severity_overrides={str(key): str(value) for key, value in overrides.items()},
            plugin_modules=_strings(raw.get("plugins", []), "plugins"),
            max_file_size_kb=(
                defaults.max_file_size_kb if size is None else _positive_int(size, "max_file_size_kb")
            ),
            max_line_length=(
                defaults.max_line_length if line is None else _positive_int(line, "max_line_length")
            ),
            follow_symlinks=(
                defaults.follow_symlinks if follow is None else _bool(follow, "follow_symlinks")
            ),
        )

    def tightened_by(self, repo: RepoConfig) -> Config:
        """Apply untrusted repository settings, in the safe direction only.

        This is a meet: each field moves toward the more restrictive of the two values,
        so the result is never weaker than ``self`` for any input. A hostile repository
        can therefore make its own scan stricter, slower, or narrower, but never laxer.

        - ``exclude`` is append-only, so operator exclusions cannot be removed.
        - ``max_file_size_kb`` and ``max_line_length`` take the minimum, so a resource
          bound cannot be raised.
        - ``follow_symlinks`` takes the conjunction, so a repository cannot make the
          scanner read through a symlink the operator did not already permit.

        Fields absent from :class:`RepoConfig` (plugins, disabled rules, severity
        overrides) are carried through from ``self`` untouched.
        """
        return Config(
            exclude=[*self.exclude, *repo.exclude],
            disabled_rules=set(self.disabled_rules),
            severity_overrides=dict(self.severity_overrides),
            plugin_modules=list(self.plugin_modules),
            max_file_size_kb=(
                self.max_file_size_kb
                if repo.max_file_size_kb is None
                else min(self.max_file_size_kb, repo.max_file_size_kb)
            ),
            max_line_length=(
                self.max_line_length
                if repo.max_line_length is None
                else min(self.max_line_length, repo.max_line_length)
            ),
            follow_symlinks=(
                self.follow_symlinks
                if repo.follow_symlinks is None
                else (self.follow_symlinks and repo.follow_symlinks)
            ),
        )
