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


MAX_HISTORY = 20


@app.command()
def chat(
    message: str = typer.Argument("", help="Message to send (omit for interactive mode)"),
    url: str = typer.Option(DEFAULT_URL, help="Synod API base URL"),
):
    """Chat with Synod. Sends code → council review, text → direct LLM reply."""
    if message:
        _do_chat(message, url, [])
        return

    history: list[dict] = []
    console.print("[bold cyan]Synod Chat[/bold cyan] — type a message, /exit to quit\n")
    console.print("[dim]Local commands: /exit, /review <file>, /scan <dir>[/dim]\n")
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
        if msg.strip().startswith("/review "):
            _local_review(msg.strip()[len("/review "):], url, history)
            if len(history) > MAX_HISTORY * 2:
                history = history[-(MAX_HISTORY * 2):]
            continue
        if msg.strip().startswith("/scan "):
            _local_scan(msg.strip()[len("/scan "):], url, history)
            if len(history) > MAX_HISTORY * 2:
                history = history[-(MAX_HISTORY * 2):]
            continue
        reply = _do_chat(msg, url, history)
        if reply is not None:
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": reply})
            if len(history) > MAX_HISTORY * 2:
                history = history[-(MAX_HISTORY * 2):]


def _do_chat(message: str, url: str, history: list[dict]) -> str | None:
    with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
        start = time.time()
        try:
            resp = httpx.post(
                f"{url}/api/v1/chat",
                json={"message": message, "history": history},
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[red]Request failed: {e}[/red]")
            return None

    data = resp.json()
    elapsed = time.time() - start
    mode_tag = "[green]council[/green]" if data["mode"] == "council" else "[blue]direct[/blue]"
    console.print(f"[dim]{mode_tag} · {elapsed:.1f}s · {data['tokens_used']} tokens[/dim]")
    console.print(data["reply"])
    console.print()
    return data["reply"]


def _run_review(code: str, filename: str, url: str, history: list[dict] | None = None) -> dict | None:
    with console.status("[cyan]Running council...[/cyan]", spinner="dots"):
        try:
            resp = httpx.post(
                f"{url}/api/v1/review",
                json={"code": code, "filename": filename, "enable_fix_loop": False},
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[red]Request failed: {e}[/red]")
            return None
    data = resp.json()
    if not data["findings"]:
        console.print("[green]No issues found.[/green]")
    else:
        for i, finding in enumerate(data["findings"], 1):
            print_finding(finding, i)
        console.print()
        print_summary(data)
    if history is not None:
        titles = [f['title'] for f in data.get("findings", [])]
        history.append({"role": "user", "content": f"/review {filename}"})
        history.append({"role": "assistant", "content": f"Reviewed {filename}: {data.get('summary', 'No issues found.')} Findings: {titles}"})
    return data


def _local_review(arg: str, url: str, history: list[dict] | None = None) -> dict | None:
    path = Path(arg)
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        return None
    return _run_review(path.read_text(), path.name, url, history)


def _local_scan(arg: str, url: str, history: list[dict] | None = None) -> dict | None:
    parts = arg.split()
    path = Path(parts[0])
    opts = {"yes": "--yes" in parts, "fix": "--fix" in parts}
    for i, p in enumerate(parts):
        if p == "--ext" and i + 1 < len(parts):
            opts["ext"] = parts[i + 1]
        if p == "--limit" and i + 1 < len(parts):
            opts["limit"] = int(parts[i + 1])
    return _run_scan(path, url, opts, history)


@app.command()
def scan(
    directory: Path = typer.Argument(..., help="Directory to scan"),
    url: str = typer.Option(DEFAULT_URL, help="Synod API base URL"),
    fix: bool = typer.Option(False, "--fix", help="Enable fix loop"),
    ext: str = typer.Option(".py", "--ext", help="File extension filter (e.g. .py, .js)"),
    limit: int = typer.Option(0, "--limit", help="Max files to scan (0 = unlimited)"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
):
    """Scan a directory and review every matching file."""
    opts = {"fix": fix, "ext": ext, "limit": limit, "yes": yes}
    _run_scan(directory, url, opts, None)


def _run_scan(directory: Path, url: str, opts: dict, history: list[dict] | None = None) -> dict | None:
    ext = opts.get("ext", ".py")
    fix = opts.get("fix", False)
    limit = opts.get("limit", 0)
    yes = opts.get("yes", False)

    if not directory.is_dir():
        console.print(f"[red]Not a directory: {directory}[/red]")
        return None

    files = sorted(directory.rglob(f"*{ext}"))
    gitignore = directory / ".gitignore"
    skip_dirs = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".eggs", "*.egg-info"}

    if gitignore.exists():
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                skip_dirs.add(line.rstrip("/"))

    files = [f for f in files if not any(p in f.parts for p in skip_dirs)]

    if limit and len(files) > limit:
        files = files[:limit]

    if not files:
        console.print(f"[yellow]No {ext} files found in {directory}[/yellow]")
        return None

    est_time = len(files) * 16
    est_tokens = len(files) * 3000
    console.print(f"[bold]Scanning {len(files)} {ext} files in {directory}...[/bold]")
    console.print(f"[dim]  Est. time: ~{est_time}s · Est. tokens: ~{est_tokens}[/dim]")
    if len(files) > 5 and not yes:
        try:
            ok = console.input("[yellow]  Continue? [Y/n]: [/yellow]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Aborted[/yellow]")
            return None
        if ok.strip().lower() not in ("", "y", "yes"):
            console.print("[yellow]Aborted[/yellow]")
            return None
    console.print()

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
        titles = [f["title"] for f in data.get("findings", [])]
        results.append({"file": str(rel), "findings_count": n, "tokens": data["tokens_used"], "time": elapsed, "titles": titles})

        if n:
            console.print(f"  [yellow]→ {rel} — {n} finding(s)[/yellow]")
        else:
            console.print(f"  [green]✓ {rel} — clean[/green]")

    console.print(f"\n[bold]Scan complete[/bold]")
    console.print(f"  Files: {len(results)}")
    console.print(f"  Findings: {total_findings}")
    console.print(f"  Tokens: {total_tokens}")
    console.print(f"  Time: {total_time:.1f}s")
    if history is not None:
        file_summaries = "; ".join(
            f"{r['file']}: {r['findings_count']} findings ({r['titles']})"
            for r in results
        )
        history.append({"role": "user", "content": f"/scan {directory}"})
        history.append({"role": "assistant", "content": f"Scanned {directory}: {total_findings} findings across {len(results)} files. Per file: {file_summaries}"})
    return {"files": len(results), "findings": total_findings, "tokens": total_tokens, "time": total_time, "file_results": results}


if __name__ == "__main__":
    app()
