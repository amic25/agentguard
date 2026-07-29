"""Per-file context made available to security rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

#: Longest line handed to a line-oriented rule. Past this, a "line" is a minified bundle
#: or generated data, not something a per-line regex can say anything useful about, and
#: it is the input that turns an ill-behaved pattern into a denial of service. Bounding
#: the input bounds every regex rule at once, including ones not yet written.
DEFAULT_MAX_LINE_LENGTH = 4096


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
    _lines: list[str] | None = field(default=None, init=False, repr=False)
    truncated_lines: int = field(default=0, init=False)

    @property
    def lines(self) -> list[str]:
        """Physical lines, each bounded by :attr:`max_line_length`.

        Truncation preserves the line *count*, so reported line numbers stay correct.
        :attr:`truncated_lines` records how much was withheld, because a bounded scan
        that reports nothing must not be mistaken for a clean one.

        Computed once. Rules call this in a loop and there are nine of them.
        """
        if self._lines is None:
            raw = self.content.splitlines()
            limit = self.max_line_length
            self.truncated_lines = sum(1 for line in raw if len(line) > limit)
            self._lines = [line[:limit] for line in raw] if self.truncated_lines else raw
        return self._lines

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
