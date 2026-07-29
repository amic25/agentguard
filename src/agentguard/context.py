"""Per-file context made available to security rules."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from agentguard.regions import Regions, analyse_javascript, analyse_manifest, analyse_python

#: Languages a rule may declare. "manifest" covers JSON, YAML, TOML, and requirements files.
KNOWN_LANGUAGES = frozenset({"python", "javascript", "typescript", "manifest"})

#: Path shapes that mean "this file exists to exercise code, or to show how to use it".
#: Credential-shaped literals here are overwhelmingly fixtures — measured as the single
#: largest false-positive source across five real agent projects.
_FIXTURE_PATH = re.compile(
    r"(?i)(?:^|/)(?:tests?|testing|__tests__|spec|specs|fixtures?|examples?|samples?|"
    r"demos?|docs?|docs_src|tutorials?|integration_tests?|e2e|benchmarks?)(?:/|$)"
)
_FIXTURE_NAME = re.compile(r"(?i)^(?:test_.*|.*_test|conftest|.*\.spec|.*\.test)$")

#: `.env.example` and friends exist to be committed and hold placeholders by convention.
#: A real `.env` does not, and is scanned at full severity.
_ENV_TEMPLATE = re.compile(r"(?i)^\.env\.(?:example|sample|template|dist|defaults?)$")

#: Paths holding code this project did not write and does not ship as its own. Findings
#: here are almost always about somebody else's release, and are not actionable in the
#: repository being scanned. Downgraded on the same footing as fixtures.
_VENDORED_PATH = re.compile(
    r"(?i)(?:^|/)(?:vendor|vendored|third[_-]?party|site-packages|dist-packages|"
    r"node_modules|bower_components|\.venv|venv|eggs|\.eggs|bundled|external)(?:/|$)"
)

#: Longest line handed to a line-oriented rule. Past this, a "line" is a minified bundle
#: or generated data, not something a per-line regex can say anything useful about, and
#: it is the input that turns an ill-behaved pattern into a denial of service. Bounding
#: the input bounds every regex rule at once, including ones not yet written.
DEFAULT_MAX_LINE_LENGTH = 4096

#: A rule may declare this as its own bound to opt out of truncation entirely. Only for
#: patterns *measured* linear — see tools/measure_linearity.py and docs/DECISIONS.md.
#: An unbounded non-linear pattern is a denial-of-service vector.
UNBOUNDED = 0


@dataclass(slots=True)
class SourceFile:
    """A decoded source file and lazy Python syntax tree."""

    path: Path
    root: Path
    content: str
    language: str
    max_line_length: int = DEFAULT_MAX_LINE_LENGTH
    _tree: ast.AST | None = field(default=None, init=False, repr=False)
    _parsed: bool = field(default=False, init=False, repr=False)
    _raw_lines: list[str] | None = field(default=None, init=False, repr=False)
    _bounded: dict[int, list[str]] = field(default_factory=dict, init=False, repr=False)
    _regions: Regions | None = field(default=None, init=False, repr=False)
    #: The bound in force for the rule currently running. Seeded from
    #: :attr:`max_line_length` and reset by the scanner before each rule, so a rule reads
    #: `source.lines` without having to know its own declaration.
    active_bound: int = field(default=DEFAULT_MAX_LINE_LENGTH, init=False)

    def __post_init__(self) -> None:
        self.active_bound = self.max_line_length

    @property
    def raw_lines(self) -> list[str]:
        """Physical lines, untruncated. Computed once."""
        if self._raw_lines is None:
            self._raw_lines = self.content.splitlines()
        return self._raw_lines

    def lines_bounded(self, bound: int) -> list[str]:
        """Lines capped at ``bound`` characters. ``UNBOUNDED`` returns them whole.

        Truncation preserves the line *count*, so reported line numbers stay correct.
        """
        if bound not in self._bounded:
            raw = self.raw_lines
            self._bounded[bound] = raw if bound <= 0 else [line[:bound] for line in raw]
        return self._bounded[bound]

    def over_bound(self, bound: int) -> list[tuple[int, int]]:
        """``(line_number, length)`` for lines longer than ``bound``. Empty if unbounded."""
        if bound <= 0:
            return []
        return [(n, len(line)) for n, line in enumerate(self.raw_lines, 1) if len(line) > bound]

    @property
    def is_fixture(self) -> bool:
        """True for test, fixture, example, and documentation files.

        Judged from the path rather than the content, because that is the signal a
        reviewer uses too: a credential under ``tests/`` is a fixture until shown
        otherwise, and a call to ``delete_file`` in ``examples/`` is a demonstration.

        The scan root's own name counts. Classifying only on the path *below* the root
        meant ``agentguard scan tests/`` saw plain filenames and treated a whole test
        suite as production code — the precise noise this policy exists to remove. Only
        the root's own name is added, never the absolute path above it, so a checkout
        living under a directory called ``test`` is not misread as one big fixture.
        """
        try:
            relative = self.relative_path.as_posix()
        except ValueError:  # pragma: no cover - path outside root
            relative = self.path.as_posix()
        rooted = f"{self.root.name}/{relative}" if self.root.name else relative
        return bool(
            _FIXTURE_PATH.search(relative)
            or _FIXTURE_PATH.search(rooted)
            or _FIXTURE_NAME.match(self.path.stem)
            or _ENV_TEMPLATE.match(self.path.name)
        )

    @property
    def is_vendored(self) -> bool:
        """True for dependency and vendored-code paths.

        A finding in `site-packages/` or `vendor/` is about someone else's release. It
        may be real, but it is not actionable where it is reported, and it drowns the
        findings that are. Downgraded on the same footing as fixtures.
        """
        try:
            relative = self.relative_path.as_posix()
        except ValueError:  # pragma: no cover - path outside root
            relative = self.path.as_posix()
        rooted = f"{self.root.name}/{relative}" if self.root.name else relative
        return bool(_VENDORED_PATH.search(relative) or _VENDORED_PATH.search(rooted))

    def regions(self) -> Regions:
        """Comment, string, docstring, and annotation spans, computed once per file."""
        if self._regions is None:
            if self.language == "python":
                self._regions = analyse_python(self.content, self.python_tree())
            elif self.language in {"javascript", "typescript"}:
                self._regions = analyse_javascript(self.content)
            else:
                self._regions = analyse_manifest(self.content)
        return self._regions

    @property
    def lines(self) -> list[str]:
        """Lines as the currently running rule should see them.

        The bound comes from that rule's declaration, applied by the scanner, so a rule
        never asks for it. A rule whose patterns are measured linear declares
        :data:`UNBOUNDED` and sees minified bundles whole — which is where inlined
        credentials live.
        """
        return self.lines_bounded(self.active_bound)

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(self.root)

    def python_tree(self) -> ast.AST | None:
        """The parsed module, or None for non-Python and unparseable files.

        Parsing uses the full content, not the bounded lines: the AST is not vulnerable
        to the backtracking the line bound exists to prevent.
        """
        if self.language != "python":
            return None
        if not self._parsed:
            try:
                self._tree = ast.parse(self.content, filename=str(self.path))
            except (SyntaxError, ValueError, RecursionError):
                self._tree = None
            self._parsed = True
        return self._tree
