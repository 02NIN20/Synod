"""Synod CLI: review, chat, and scan from the terminal."""

import time
import httpx
import typer
from pathlib import Path
from cli.display import console, print_finding, print_summary, print_code

app = typer.Typer(help="Synod - multi-agent code review CLI")

DEFAULT_URL = "http://47.84.227.185:8000"


@app.command()
def review(
    filepath: Path = typer.Argument(..., help="Path to the code file to review"),
    url: str = typer.Option(DEFAULT_URL, help="Synod API base URL"),
    fix: bool = typer.Option(False, "--fix", help="Enable fix loop (Smith)"),
    show_code: bool = typer.Option(False, "--show-code", help="Print the code before review"),
):
    """Run a full multi-agent code review against Synod."""
    if not filepath.exists():
        console.print(f"[red]File not found: {filepath}[/red]")
        raise typer.Exit(1)

    code = filepath.read_text()

    if show_code:
        print_code(code, filepath.name)

    console.print(f"\n[bold cyan]Synod[/bold cyan] reviewing [bold]{filepath.name}[/bold]...\n")

    with console.status("[cyan]Running council...[/cyan]", spinner="dots"):
        start = time.time()
        try:
            resp = httpx.post(
                f"{url}/api/v1/review",
                json={"code": code, "filename": filepath.name, "enable_fix_loop": fix},
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[red]Request failed: {e}[/red]")
            raise typer.Exit(1)

    data = resp.json()
    elapsed = time.time() - start

    console.print(f"[green]Done in {elapsed:.1f}s[/green]\n")

    if not data["findings"]:
        console.print("[green]No issues found.[/green]")
        return

    for i, finding in enumerate(data["findings"], 1):
        print_finding(finding, i)

    console.print()
    print_summary(data)


@app.command()
def health(url: str = typer.Option(DEFAULT_URL, help="Synod API base URL")):
    """Check if Synod is running."""
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        resp.raise_for_status()
        console.print(f"[green]OK[/green] - {resp.json()}")
    except httpx.HTTPError as e:
        console.print(f"[red]Synod unreachable: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def chat(
    message: str = typer.Argument("", help="Message to send (omit for interactive mode)"),
    url: str = typer.Option(DEFAULT_URL, help="Synod API base URL"),
):
    """Chat with Synod. Sends code → council review, text → direct LLM reply."""
    if message:
        _do_chat(message, url)
        return

    console.print("[bold cyan]Synod Chat[/bold cyan] — type a message, /exit to quit\n")
    while True:
        try:
            msg = console.input("[bold]>>> [/bold]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Bye![/yellow]")
            return
        if not msg:
            continue
        if msg.strip() == "/exit":
            console.print("[yellow]Bye![/yellow]")
            return
        _do_chat(msg, url)


def _do_chat(message: str, url: str):
    with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
        start = time.time()
        try:
            resp = httpx.post(
                f"{url}/api/v1/chat",
                json={"message": message},
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[red]Request failed: {e}[/red]")
            return

    data = resp.json()
    elapsed = time.time() - start
    mode_tag = "[green]council[/green]" if data["mode"] == "council" else "[blue]direct[/blue]"
    console.print(f"[dim]{mode_tag} · {elapsed:.1f}s · {data['tokens_used']} tokens[/dim]")
    console.print(data["reply"])
    console.print()


@app.command()
def scan(
    directory: Path = typer.Argument(..., help="Directory to scan"),
    url: str = typer.Option(DEFAULT_URL, help="Synod API base URL"),
    fix: bool = typer.Option(False, "--fix", help="Enable fix loop"),
    ext: str = typer.Option(".py", "--ext", help="File extension filter (e.g. .py, .js)"),
):
    """Scan a directory and review every matching file."""
    if not directory.is_dir():
        console.print(f"[red]Not a directory: {directory}[/red]")
        raise typer.Exit(1)

    files = sorted(directory.rglob(f"*{ext}"))
    gitignore = directory / ".gitignore"
    skip_dirs = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".eggs", "*.egg-info"}

    if gitignore.exists():
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                skip_dirs.add(line.rstrip("/"))

    files = [f for f in files if not any(p in f.parts for p in skip_dirs)]

    if not files:
        console.print(f"[yellow]No {ext} files found in {directory}[/yellow]")
        return

    console.print(f"[bold]Scanning {len(files)} {ext} files in {directory}...[/bold]\n")

    total_findings = 0
    total_tokens = 0
    total_time = 0.0
    results = []

    for f in files:
        rel = f.relative_to(directory)
        with console.status(f"[cyan]  {rel}[/cyan]", spinner="dots"):
            start = time.time()
            try:
                resp = httpx.post(
                    f"{url}/api/v1/review",
                    json={"code": f.read_text(), "filename": f.name, "enable_fix_loop": fix},
                    timeout=120,
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                console.print(f"  [red]✗ {rel} — request failed[/red]")
                continue

        data = resp.json()
        elapsed = time.time() - start
        n = data["total_findings"]
        total_findings += n
        total_tokens += data["tokens_used"]
        total_time += elapsed
        results.append((rel, n, data["tokens_used"], elapsed))

        if n:
            console.print(f"  [yellow]→ {rel} — {n} finding(s)[/yellow]")
        else:
            console.print(f"  [green]✓ {rel} — clean[/green]")

    console.print(f"\n[bold]Scan complete[/bold]")
    console.print(f"  Files: {len(results)}")
    console.print(f"  Findings: {total_findings}")
    console.print(f"  Tokens: {total_tokens}")
    console.print(f"  Time: {total_time:.1f}s")


if __name__ == "__main__":
    app()
