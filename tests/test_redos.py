"""AG004's rewrite must be faster without deciding anything differently.

The original pattern was cubic in line length. Fixing it is a safety change, so it had to
land before the corpus and benchmark exist — which means it must be proven to change no
detection outcome at all. The differential test below is that proof: the old pattern and
the new two-step search are asserted to accept exactly the same lines, and to report the
same column, over every input we can produce.
"""

from __future__ import annotations

import re
import time

import pytest

from agentguard.config import Config
from agentguard.context import DEFAULT_MAX_LINE_LENGTH, SourceFile
from agentguard.rules.code import PromptInjectionRule
from agentguard.scanner import Scanner

_SOURCES = PromptInjectionRule._sources

#: The pattern exactly as it stood before the rewrite, kept only as a test oracle.
ORIGINAL = re.compile(
    rf"(?i)(?:prompt|system_message|instructions?)\s*=.*"
    rf"(?:f['\"].*\{{{_SOURCES}\}}|\.format\([^)]*{_SOURCES}|\+\s*{_SOURCES})"
)
ORIGINAL_TEMPLATE = re.compile(rf"(?i)(?:content|prompt)\s*(?::|=)\s*`[^`]*\$\{{{_SOURCES}\}}")


def _original_match(line: str) -> re.Match[str] | None:
    return ORIGINAL.search(line) or ORIGINAL_TEMPLATE.search(line)


CASES = [
    # --- should match -------------------------------------------------------------
    'prompt = f"Summarize: {user_input}"',
    'prompt=f"{request}"',
    "system_message = f'hello {web_content} there'",
    'instructions = "x".format(user_message)',
    'instruction = "x".format(document)',
    "prompt = base + user_input",
    "prompt = base +   tool_output",
    'PROMPT = F"{USER_INPUT}"',
    "const prompt = `Read ${web_content}`",
    "content: `${page}`",
    'prompt   =   f"lots of text here {message.content} and more"',
    'prompt = f"{result}"',
    # --- should not match ---------------------------------------------------------
    "prompt = 'a static string'",
    "prompt = f'{safe_constant}'",
    "x = f'{user_input}'",
    "prompt_template.format(SAFE)",
    "# prompt = f'{user_input}'  (this is a comment, still matches by design)",
    "prompt",
    "",
    "=",
    "prompt =",
    "prompt = f'{",
    "prompt = f'{user_input",
    "const prompt = `no interpolation`",
    "content: `${safe}`",
    "prompt = base + safe_value",
    # --- adversarial / near-miss --------------------------------------------------
    "prompt=f'" * 40 + "{req",
    "prompt=f'" * 40 + "{request}",
    "prompt = " + "f'" * 30 + "{user_input}",
    "prompt = " + "x" * 200 + " + user_input",
    "prompt = " + "x" * 200 + " + not_a_source",
    "instructions=" + ".format(" * 20 + "user_input",
]


@pytest.mark.parametrize("line", CASES)
def test_rewrite_accepts_exactly_the_same_lines(line: str) -> None:
    rule = PromptInjectionRule()
    old, new = _original_match(line), rule._match(line)
    assert (old is None) == (new is None), f"acceptance differs for {line!r}"
    if old is not None and new is not None:
        assert old.start() == new.start(), f"reported column differs for {line!r}"


def test_rewrite_agrees_on_generated_inputs() -> None:
    """Cover combinations the hand-written cases would not think to include."""
    rule = PromptInjectionRule()
    prefixes = ["prompt", "system_message", "instruction", "instructions", "PROMPT", "notaprompt"]
    seps = ["=", " = ", "  =", ":"]
    bodies = ["f'{user_input}'", 'f"{req}"', ".format(document)", "+ web_content", "'static'", ""]
    padding = ["", "x" * 30, "# " * 10]

    checked = 0
    for prefix in prefixes:
        for sep in seps:
            for body in bodies:
                for pad in padding:
                    line = f"{prefix}{sep}{pad}{body}"
                    old, new = _original_match(line), rule._match(line)
                    assert (old is None) == (new is None), f"acceptance differs for {line!r}"
                    if old is not None and new is not None:
                        assert old.start() == new.start(), f"column differs for {line!r}"
                    checked += 1
    assert checked > 400


def test_pathological_line_is_fast() -> None:
    """The original took ~34s on 28KB of this. Bound generously to stay honest on slow CI."""
    rule = PromptInjectionRule()
    line = "prompt=f'" * 3200 + "{req"  # ~28 KB, one line

    start = time.perf_counter()
    rule._match(line)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"AG004 took {elapsed:.2f}s on a 28KB line; the cubic blowup is back"


def test_scan_of_a_pathological_file_is_fast(project) -> None:  # type: ignore[no-untyped-def]
    """End to end, through the scanner, with every rule enabled."""
    (project / "minified.js").write_text("prompt=f'" * 3200 + "{req", encoding="utf-8")

    start = time.perf_counter()
    result = Scanner(Config()).scan(project)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"scanning one pathological file took {elapsed:.2f}s"
    assert result.completed


# --- the engine-level bound ----------------------------------------------------------


def test_long_lines_are_bounded_and_the_bound_is_reported(project) -> None:  # type: ignore[no-untyped-def]
    """A silent cap would let a bounded scan pass for a complete one."""
    (project / "big.js").write_text("a" * (DEFAULT_MAX_LINE_LENGTH * 3), encoding="utf-8")
    result = Scanner(Config()).scan(project)
    assert result.truncated_lines == 1


def test_line_bound_applies_to_rule_input(project) -> None:  # type: ignore[no-untyped-def]
    source = SourceFile(project / "x.py", project, "b" * 100 + "\nshort\n", "python", max_line_length=10)
    assert [len(line) for line in source.lines] == [10, 5]
    assert source.truncated_lines == 1


def test_line_bound_preserves_line_numbering(project) -> None:  # type: ignore[no-untyped-def]
    content = "x" * 50 + "\nimport os\nos.system(user_input)\n"
    source = SourceFile(project / "x.py", project, content, "python", max_line_length=10)
    assert len(source.lines) == 3
    assert source.lines[2] == "os.system("


def test_bound_defaults_are_not_hit_by_ordinary_code() -> None:
    """4096 is not a limit real source runs into; only generated or minified files do."""
    assert DEFAULT_MAX_LINE_LENGTH >= 4096
