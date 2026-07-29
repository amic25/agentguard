"""AgentGuard command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentguard import __version__
from agentguard.config import Config
from agentguard.models import Severity
from agentguard.reporters import REPORTERS, render_terminal
from agentguard.rules import BUILTIN_RULES
from agentguard.scanner import Scanner

app = typer.Typer(
    name="agentguard",
    help="Find security weaknesses in Python and JavaScript/TypeScript AI agent projects.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
error_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"AgentGuard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Scan AI agent code before it reaches production."""


@app.command()
def scan(
    target: Path = typer.Argument(
        Path("."), exists=True, readable=True, help="File or project directory to scan."
    ),
    format: str = typer.Option("terminal", "--format", "-f", help="terminal, json, markdown, or sarif."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write the report to this file."),
    fail_on: str = typer.Option(
        "high", help="Exit 1 when this severity or higher is found; use none to disable."
    ),
    fail_on_incomplete: bool = typer.Option(
        False,
        "--fail-on-incomplete",
        help="Also exit 2 when any line was too long to be read in full by every rule.",
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to .agentguard.yml."),
    exclude: list[str] = typer.Option([], "--exclude", help="Additional glob to exclude; repeat as needed."),
) -> None:
    """Scan a project and produce an actionable security report."""
    report_format = format.lower()
    if report_format not in {"terminal", *REPORTERS}:
        raise typer.BadParameter("format must be terminal, json, markdown, or sarif", param_hint="--format")
    try:
        settings = Config.load(config, target.resolve() if target.is_dir() else target.resolve().parent)
        settings.exclude.extend(exclude)
        result = Scanner(settings).scan(target)
    except (OSError, ValueError, RuntimeError) as exc:
        error_console.print(f"[bold red]AgentGuard could not scan the target:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    if report_format == "terminal":
        if output:
            raise typer.BadParameter(
                "--output requires json, markdown, or sarif format", param_hint="--output"
            )
        render_terminal(result, console)
    else:
        rendered = REPORTERS[report_format](result)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            error_console.print(f"Report written to [bold]{output}[/bold]")
        else:
            typer.echo(rendered)
    if fail_on.lower() != "none":
        try:
            threshold = Severity.parse(fail_on)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--fail-on") from exc
    if fail_on_incomplete and not result.fully_covered:
        # Opt-in. Truncation is declared in every report by default rather than gating,
        # because a bounded read is a known limitation, not a malfunction. A caller who
        # needs total coverage asks for it and gets exit 2 - the same code as any other
        # "this result is not a clean bill of health".
        error_console.print(
            f"[bold red]Coverage incomplete:[/bold red] {result.truncated_lines} line(s) "
            "were not read in full; --fail-on-incomplete was requested."
        )
        raise typer.Exit(code=2)
    if not result.completed:
        # Ranked above --fail-on: CI must be able to tell "found problems" (1) from
        # "the tool did not finish, so absence of findings means nothing" (2).
        error_console.print(
            f"[bold red]Scan incomplete:[/bold red] {len(result.errors)} error(s); "
            "results are not a clean bill of health."
        )
        raise typer.Exit(code=2)
    if fail_on.lower() != "none" and any(finding.severity >= threshold for finding in result.findings):
        raise typer.Exit(code=1)


@app.command("rules")
def list_rules() -> None:
    """List built-in rule identifiers and severities."""
    table = Table("Rule", "Severity", "Category", "Description")
    for kind in BUILTIN_RULES:
        item = kind.metadata
        table.add_row(item.id, item.severity.name.title(), item.category, item.description)
    console.print(table)


@app.command("init")
def init_config(
    path: Path = typer.Option(Path(".agentguard.yml"), "--path", help="Configuration file to create."),
) -> None:
    """Create a documented starter configuration."""
    if path.exists():
        error_console.print(f"[red]Refusing to overwrite existing file:[/red] {path}")
        raise typer.Exit(code=2)
    path.write_text(
        "# AgentGuard configuration\n"
        "#\n"
        "# A config discovered in the repository being scanned is treated as untrusted\n"
        "# input: it may only make a scan stricter. Excludes are added to (never removed\n"
        "# from) the defaults, max_file_size_kb may only be lowered, and follow_symlinks\n"
        "# may only be turned off.\n"
        "#\n"
        "# plugins, disabled_rules, and severity_overrides can weaken a scan or execute\n"
        "# code, so they are rejected here. To use them, vouch for this file explicitly:\n"
        "#     agentguard scan . --config .agentguard.yml\n"
        "exclude:\n  - tests/fixtures/**\n"
        "max_file_size_kb: 1024\n"
        "follow_symlinks: false\n",
        encoding="utf-8",
    )
    console.print(f"Created [bold]{path}[/bold]")
