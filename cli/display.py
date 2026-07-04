"""Rich-based display for Synod CLI."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.syntax import Syntax

console = Console()

SEVERITY_COLOR = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "dim",
}

AGENT_COLOR = {
    "cartographer": "cyan",
    "inspector": "blue",
    "sentinel": "magenta",
    "smith": "green",
}


def agent_spinner(label: str):
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )
    return progress, progress.add_task(label, total=None)


def print_finding(finding: dict, index: int):
    color = SEVERITY_COLOR.get(finding["impact"], "white")
    agent_color = AGENT_COLOR.get(finding["agent"], "white")

    header = f"[{color}]{finding['impact'].upper()}[/{color}] · [{agent_color}]{finding['agent']}[/{agent_color}]"
    if finding.get("cwe"):
        header += f" · {finding['cwe']}"

    body = f"[bold]{finding['title']}[/bold]\n\n{finding['detail']}"
    if finding.get("proposal"):
        body += f"\n\n[dim]Proposal:[/dim]\n{finding['proposal']}"

    console.print(Panel(body, title=f"[{index}] {header}", border_style=color, expand=False))


def print_summary(response: dict):
    table = Table(show_header=False, box=None)
    table.add_row("Session", response["session_id"])
    table.add_row("Findings", str(response["total_findings"]))
    table.add_row("Tokens used", str(response["tokens_used"]))
    table.add_row("Time", f'{response["time_seconds"]}s')
    console.print(table)
    console.print(f"\n[bold]{response['summary']}[/bold]\n")

    if response.get("errors"):
        console.print("[yellow]Warnings:[/yellow]")
        for err in response["errors"]:
            console.print(f"  - {err}")


def print_code(code: str, filename: str = "code.py"):
    lexer = "python" if filename.endswith(".py") else "text"
    syntax = Syntax(code, lexer, theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=filename, border_style="dim"))


WELCOME = """[bold cyan]╔══════════════════════════════════════╗
║           Synod Chat Mode            ║
║  Multi-Agent Code Review Council     ║
╚══════════════════════════════════════╝[/bold cyan]

Paste Python code, then type [bold]---[/bold] on a new line and press Enter.

Commands:
  [bold]/fix[/bold]    — enable fix loop for next review
  [bold]/nofix[/bold]  — disable fix loop
  [bold]/exit[/bold]   — quit
"""
