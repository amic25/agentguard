"""Where in a file a position sits: comment, docstring, string, or annotation.

Rules kept rediscovering that a match inside a comment or a docstring is not a finding,
and kept getting it wrong, because each one re-implemented the guess with a slightly
different regex. This computes it once per file from the language's own grammar, so a
rule declares *what it does not want to match inside* and the engine enforces it.

Positions are (line, column), both 1-based, matching :class:`~agentguard.models.Location`.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field

#: Region names a rule may list in ``RuleMetadata.ignore_regions``.
REGION_NAMES = frozenset({"comment", "docstring", "string", "annotation"})

_JS_TOKENS = re.compile(
    r"""
    (?P<line_comment>//[^\n]*)
  | (?P<block_comment>/\*.*?\*/)
  | (?P<string>'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`)
    """,
    re.VERBOSE | re.DOTALL,
)
_HASH_COMMENT = re.compile(r"(?<!\\)#[^\n]*")


@dataclass(slots=True)
class Regions:
    """Half-open ``[start, end)`` column spans per 1-based line, keyed by region name."""

    spans: dict[str, dict[int, list[tuple[int, int]]]] = field(default_factory=dict)
    call_lines: frozenset[int] = frozenset()

    def add(self, name: str, line: int, start: int, end: int) -> None:
        self.spans.setdefault(name, {}).setdefault(line, []).append((start, end))

    def contains(self, name: str, line: int, column: int) -> bool:
        return any(start <= column < end for start, end in self.spans.get(name, {}).get(line, ()))

    def any_of(self, names: frozenset[str], line: int, column: int) -> bool:
        return any(self.contains(name, line, column) for name in names)


def _mark_multiline(regions: Regions, name: str, token: tokenize.TokenInfo) -> None:
    (start_row, start_col), (end_row, end_col) = token.start, token.end
    if start_row == end_row:
        regions.add(name, start_row, start_col + 1, end_col + 1)
        return
    regions.add(name, start_row, start_col + 1, 10**9)
    for row in range(start_row + 1, end_row):
        regions.add(name, row, 1, 10**9)
    regions.add(name, end_row, 1, end_col + 1)


def _python_docstring_tokens(tree: ast.AST) -> set[tuple[int, int]]:
    """Start positions of docstring literals: the first statement of a module or def."""
    found: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add((first.value.lineno, first.value.col_offset))
    return found


def _python_annotations(regions: Regions, tree: ast.AST) -> None:
    """Annotation positions, so `token: "contextvars.Token[Any]"` is not a credential."""
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        candidate: ast.expr | None = None
        if isinstance(node, ast.AnnAssign | ast.arg):
            candidate = node.annotation
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            candidate = node.returns
        if candidate is not None:
            nodes.append(candidate)

    for annotation in nodes:
        start_line, start_col = annotation.lineno, annotation.col_offset + 1
        end_line = annotation.end_lineno or start_line
        end_col = annotation.end_col_offset
        if end_line == start_line and end_col is not None:
            regions.add("annotation", start_line, start_col, end_col + 1)
            continue
        regions.add("annotation", start_line, start_col, 10**9)
        for row in range(start_line + 1, end_line + 1):
            end = end_col + 1 if (row == end_line and end_col is not None) else 10**9
            regions.add("annotation", row, 1, end)


def analyse_python(content: str, tree: ast.AST | None) -> Regions:
    regions = Regions()
    docstrings = _python_docstring_tokens(tree) if tree is not None else set()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        # Unparseable input still deserves the AST-derived regions we managed to get.
        tokens = []
    for token in tokens:
        if token.type == tokenize.COMMENT:
            _mark_multiline(regions, "comment", token)
        elif token.type == tokenize.STRING:
            name = "docstring" if (token.start[0], token.start[1]) in docstrings else "string"
            _mark_multiline(regions, name, token)
    if tree is not None:
        _python_annotations(regions, tree)
        regions.call_lines = frozenset(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call))
    return regions


def analyse_javascript(content: str) -> Regions:
    regions = Regions()
    line_starts = [0]
    for index, character in enumerate(content):
        if character == "\n":
            line_starts.append(index + 1)

    def locate(offset: int) -> tuple[int, int]:
        low, high = 0, len(line_starts) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if line_starts[mid] <= offset:
                low = mid
            else:
                high = mid - 1
        return low + 1, offset - line_starts[low] + 1

    for match in _JS_TOKENS.finditer(content):
        kind = match.lastgroup or ""
        name = "string" if kind == "string" else "comment"
        start_line, start_col = locate(match.start())
        end_line, end_col = locate(match.end())
        if start_line == end_line:
            regions.add(name, start_line, start_col, end_col)
        else:
            regions.add(name, start_line, start_col, 10**9)
            for row in range(start_line + 1, end_line):
                regions.add(name, row, 1, 10**9)
            regions.add(name, end_line, 1, end_col)
    return regions


def analyse_manifest(content: str) -> Regions:
    """YAML and TOML share `#` comments. JSON has none, and never matches."""
    regions = Regions()
    for number, line in enumerate(content.splitlines(), 1):
        match = _HASH_COMMENT.search(line)
        if match:
            regions.add("comment", number, match.start() + 1, len(line) + 2)
    return regions
