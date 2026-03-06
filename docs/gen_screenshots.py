#!/usr/bin/env python3
"""Generate SVG screenshots for README / articles using Rich's export_svg."""

import sys
sys.path.insert(0, ".")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich import box

WIDTH = 90


def gen_dashboard():
    console = Console(record=True, width=WIDTH, force_terminal=True)
    table = Table(box=box.ROUNDED, show_lines=False, padding=(0, 1))
    table.add_column("Name", style="bold cyan", no_wrap=True, max_width=20)
    table.add_column("Branch", style="magenta", no_wrap=True, max_width=15)
    table.add_column("Last Commit", no_wrap=True, max_width=10)
    table.add_column("Status", no_wrap=True, justify="center")
    table.add_column("Language", no_wrap=True, max_width=12)
    table.add_column("Commits", justify="right")
    table.add_column("Remote", no_wrap=True)

    data = [
        ("codemaster",  "main",   "10m ago",  ("bold red", "●1"),  "Python",      "15", "github ↑3"),
        ("quant",       "main",   "2h ago",   ("bold red", "●15"), "Python",      "89", "github"),
        ("SEIR",        "main",   "4d ago",   ("bold red", "●26"), "Python",     "124", "github"),
        ("simonaCI",    "feature","1d ago",   ("green", "✓"),      "C++",        "203", "gitlab ↑4"),
        ("scip",        "master", "8d ago",   ("bold red", "●4"),  "C/C++",   "48542", "github"),
        ("petsc",       "main",   "1mo ago",  ("green", "✓"),      "C",       "32891", "github"),
        ("OpenPollen",  "main",   "5d ago",   ("green", "✓"),      "TypeScript",  "67", "github"),
        ("managerAgent","main",   "3h ago",   ("bold red", "●4"),  "Python",      "42", "github ↑2"),
    ]
    for name, branch, last, (sty, status), lang, commits, remote in data:
        if "m ago" in last or "h ago" in last:
            t = Text(last, style="green")
        elif "d ago" in last:
            t = Text(last, style="yellow")
        else:
            t = Text(last, style="dim")
        table.add_row(name, branch, t, Text(status, style=sty), lang, commits, remote)

    panel = Panel(table,
        title=f"[bold]CodeBoard[/bold] ── ~/Code ── {len(data)} repos",
        subtitle="● = uncommitted  ✓ = clean",
        border_style="blue")
    console.print(panel)
    return console.export_svg(title="cb — Dashboard")


def gen_health():
    console = Console(record=True, width=WIDTH, force_terminal=True)
    lines = []
    lines.append("")
    lines.append("  [bold yellow]⚠ Uncommitted changes[/bold yellow] (12 repos)")
    lines.append("    [cyan]codeAgent[/cyan] (89) | [cyan]SEIR[/cyan] (26) | [cyan]quant[/cyan] (15) | [cyan]managerAgent[/cyan] (4) | ...")
    lines.append("")
    lines.append("  [bold yellow]⚠ Unpushed commits[/bold yellow] (3 repos)")
    lines.append("    [cyan]codemaster[/cyan] (↑3) | [cyan]simonaCI[/cyan] (↑4) | [cyan]managerAgent[/cyan] (↑2)")
    lines.append("")
    lines.append("  [dim]○ No remote[/dim] (4 repos)")
    lines.append("    autoClaude | autocode | computer_use | BMB")
    lines.append("")
    lines.append("  [dim]○ Inactive >30d[/dim] (6 repos)")
    lines.append("    SimonaAgent | simona_api | thermoGPUpaper | nano-vllm | ...")
    lines.append("")
    lines.append("  [green]✓ All clean[/green] (23 repos)")
    lines.append("")

    panel = Panel("\n".join(lines), title="[bold]Health Report[/bold]", border_style="blue")
    console.print(panel)
    return console.export_svg(title="cb health")


def gen_activity():
    console = Console(record=True, width=WIDTH, force_terminal=True)
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Repo", style="bold cyan", no_wrap=True)
    table.add_column("Author", style="magenta")
    table.add_column("Message")

    commits = [
        ("10m ago",  "codemaster",  "Shaoyi Yang", "feat: add shell completion generation"),
        ("2h ago",   "quant",       "Shaoyi Yang", "fix: handle missing data in strategy"),
        ("3h ago",   "managerAgent","Shaoyi Yang", "feat: add retry logic for API calls"),
        ("1d ago",   "simonaCI",    "Shaoyi Yang", "chore: update CI pipeline config"),
        ("2d ago",   "SEIR",        "Shaoyi Yang", "feat: add vaccination compartment"),
        ("4d ago",   "quant",       "Shaoyi Yang", "refactor: simplify position tracker"),
        ("5d ago",   "OpenPollen",  "Shaoyi Yang", "docs: update API documentation"),
        ("6d ago",   "SEIR",        "Shaoyi Yang", "fix: normalize population weights"),
    ]
    for t, repo, author, msg in commits:
        table.add_row(t, repo, author, msg)

    panel = Panel(table, title="[bold]Activity[/bold] ── last 8 commits", border_style="blue")
    console.print(panel)
    return console.export_svg(title="cb activity")


def gen_batch_ops():
    """Simulate batch pull output."""
    console = Console(record=True, width=WIDTH, force_terminal=True)
    console.print("[bold]Pulling 12 repos with remote[/bold]\n")
    results = [
        ("green",  "✓ Updated",     "codemaster",    "main ← origin/main (3 commits)"),
        ("green",  "✓ Updated",     "quant",         "main ← origin/main (1 commit)"),
        ("dim",    "─ Up to date",  "SEIR",          ""),
        ("dim",    "─ Up to date",  "simonaCI",      ""),
        ("dim",    "─ Up to date",  "scip",          ""),
        ("green",  "✓ Updated",     "OpenPollen",    "main ← origin/main (2 commits)"),
        ("dim",    "─ Up to date",  "petsc",         ""),
        ("dim",    "─ Up to date",  "managerAgent",  ""),
        ("red",    "✗ Failed",      "sundials",      "fatal: not a git repository"),
        ("dim",    "─ Up to date",  "simonasolver",  ""),
        ("dim",    "─ Up to date",  "SDD",           ""),
        ("dim",    "─ Up to date",  "processOP",     ""),
    ]
    for style, status, name, detail in results:
        line = f"  [{style}]{status}[/{style}]  [bold cyan]{name:<16}[/bold cyan]"
        if detail:
            line += f"  [dim]{detail}[/dim]"
        console.print(line)

    console.print("\n[bold green]3[/bold green] updated  [bold red]1[/bold red] failed  [dim]8 up to date[/dim]")
    return console.export_svg(title="cb pull")


def gen_stats():
    """Simulate stats output."""
    console = Console(record=True, width=WIDTH, force_terminal=True)

    # Summary row
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column(justify="right", style="bold cyan")
    summary.add_row("Total repos", "48")
    summary.add_row("Active (30d)", "22")
    summary.add_row("Has remote", "42")
    summary.add_row("Total commits", "89,431")

    # Language distribution
    lang_tbl = Table(title="[bold]Language Distribution[/bold]", box=box.SIMPLE, show_header=True, padding=(0, 1))
    lang_tbl.add_column("Language", style="bold cyan")
    lang_tbl.add_column("Repos", justify="right")
    lang_tbl.add_column("", min_width=20)
    langs = [
        ("Python", "14", "████████████████████"),
        ("C++",     "9", "████████████"),
        ("C",       "5", "███████"),
        ("Julia",   "4", "█████"),
        ("TypeScript","4","█████"),
        ("Java",    "3", "████"),
        ("Shell",   "2", "██"),
        ("LaTeX",   "2", "██"),
        ("Other",   "5", "███████"),
    ]
    for lang, n, bar in langs:
        lang_tbl.add_row(lang, n, Text(bar, style="green"))

    # Weekly top
    week_tbl = Table(title="[bold]Weekly Top[/bold]", box=box.SIMPLE, show_header=True, padding=(0, 1))
    week_tbl.add_column("Repo", style="bold cyan")
    week_tbl.add_column("Commits", justify="right", style="bold yellow")
    week_tbl.add_row("codemaster", "12")
    week_tbl.add_row("managerAgent", "8")
    week_tbl.add_row("quant", "5")
    week_tbl.add_row("simonaCI", "3")
    week_tbl.add_row("SEIR", "2")

    panel = Panel(summary, title="[bold]Statistics[/bold]", border_style="blue", subtitle="48 repos scanned")
    console.print(panel)
    console.print(lang_tbl)
    console.print(week_tbl)
    return console.export_svg(title="cb stats")


def gen_detail():
    """Simulate single repo detail output."""
    console = Console(record=True, width=WIDTH, force_terminal=True)

    info_lines = []
    info_lines.append(f"  [bold]Path[/bold]          ~/Code/quant")
    info_lines.append(f"  [bold]Remote[/bold]        git@github.com:ysyecust/quant.git")
    info_lines.append(f"  [bold]Branch[/bold]        main (+2 branches)")
    info_lines.append(f"  [bold]Commits[/bold]       [bold cyan]89[/bold cyan]  (this week 5 / this month 18)")
    info_lines.append(f"  [bold]Contributors[/bold]  1 (Shaoyi Yang)")
    info_lines.append(f"  [bold]Language[/bold]      Python 85%, Shell 10%, Markdown 5%")
    info_lines.append(f"  [bold]Tags[/bold]          3 tags (latest: v0.2.1)")
    info_lines.append(f"  [bold]Status[/bold]        [bold red]●15 uncommitted[/bold red]")

    panel = Panel("\n".join(info_lines), title="[bold cyan]quant[/bold cyan]", border_style="blue")
    console.print(panel)

    # Recent commits
    tbl = Table(title="[bold]Recent Commits[/bold]", box=box.SIMPLE, show_header=False, padding=(0, 1))
    tbl.add_column(style="dim", no_wrap=True)
    tbl.add_column()
    commits = [
        ("2h ago",  "[green]feat:[/green] add Bollinger band strategy"),
        ("1d ago",  "[green]feat:[/green] portfolio risk metrics"),
        ("2d ago",  "[yellow]fix:[/yellow] handle missing OHLCV data"),
        ("3d ago",  "[green]feat:[/green] backtest engine with slippage"),
        ("5d ago",  "[blue]refactor:[/blue] simplify position tracker"),
    ]
    for t, msg in commits:
        tbl.add_row(t, msg)
    console.print(tbl)

    # Activity sparkline
    console.print("\n  [bold]Activity[/bold]  ▁▂▃▁▅▇█▅▃▂▁▁▃▅▇▅▃▂▁▂▃▅▃▁  [dim](24 weeks)[/dim]")

    return console.export_svg(title="cb detail quant")


def gen_filter():
    """Simulate filtered dashboard."""
    console = Console(record=True, width=WIDTH, force_terminal=True)

    # Show the command
    console.print("[dim]$[/dim] [bold]cb --filter simona --sort changes[/bold]\n")

    table = Table(box=box.ROUNDED, show_lines=False, padding=(0, 1))
    table.add_column("Name", style="bold cyan", no_wrap=True, max_width=20)
    table.add_column("Branch", style="magenta", no_wrap=True, max_width=18)
    table.add_column("Last Commit", no_wrap=True)
    table.add_column("Status", no_wrap=True, justify="center")
    table.add_column("Language", no_wrap=True)
    table.add_column("Remote", no_wrap=True)

    data = [
        ("simona_vision",    "main",             "12d ago", ("bold red", "●10"), "Python",     "gitlab"),
        ("SimonaRL",         "main",             "15d ago", ("bold red", "●11"), "Python",     "github"),
        ("simona_api",       "dev-sit",          "20d ago", ("bold red", "●6"),  "Python",     "gitlab"),
        ("SimonaAgent",      "main",             "22d ago", ("bold red", "●6"),  "Python",     "github"),
        ("simonasolver",     "main",             "28d ago", ("bold red", "●3"),  "C++",        "github"),
        ("simona",           "dev-uat-2025",     "29d ago", ("green", "✓"),      "C++",        "gitlab"),
        ("simona_log",       "main",             "1mo ago", ("bold red", "●1"),  "Python",     "gitlab"),
        ("simona_auto",      "main",             "2mo ago", ("bold red", "●1"),  "Python",     "local"),
    ]
    for name, branch, last, (sty, status), lang, remote in data:
        t = Text(last, style="yellow" if "d ago" in last else "dim")
        table.add_row(name, branch, t, Text(status, style=sty), lang, remote)

    panel = Panel(table,
        title="[bold]CodeBoard[/bold] ── ~/Code ── [yellow]simona[/yellow] ── 8 repos",
        subtitle="● = uncommitted  ✓ = clean",
        border_style="blue")
    console.print(panel)
    return console.export_svg(title="cb --filter simona")


def gen_grep():
    """Simulate cross-repo grep."""
    console = Console(record=True, width=WIDTH, force_terminal=True)

    console.print("[dim]$[/dim] [bold]cb grep \"TODO\" --filter simona[/bold]\n")

    results = [
        ("SimonaAgent",   "src/agent.py",       "42", "# TODO: add retry with exponential backoff"),
        ("SimonaAgent",   "src/tools.py",        "18", "# TODO: cache tool results"),
        ("simona_api",    "routes/solve.py",     "67", "# TODO: validate input schema"),
        ("simona_api",    "routes/solve.py",    "103", "# TODO: add rate limiting"),
        ("simonasolver",  "src/solver.cpp",     "291", "// TODO: parallelize branch-and-bound"),
        ("simona_vision", "detect.py",           "55", "# TODO: handle multi-page PDF"),
        ("SimonaRL",      "env/chemical.py",     "89", "# TODO: normalize reward scale"),
    ]

    for repo, file, line, content in results:
        console.print(f"  [bold cyan]{repo:<16}[/bold cyan] [dim]{file}:{line}[/dim]")
        console.print(f"                   [yellow]{content}[/yellow]")

    console.print(f"\n[dim]7 matches across 5 repos[/dim]")
    return console.export_svg(title="cb grep TODO")


if __name__ == "__main__":
    generators = [
        ("dashboard", gen_dashboard),
        ("health",    gen_health),
        ("activity",  gen_activity),
        ("batch-ops", gen_batch_ops),
        ("stats",     gen_stats),
        ("detail",    gen_detail),
        ("filter",    gen_filter),
        ("grep",      gen_grep),
    ]
    for name, fn in generators:
        svg = fn()
        path = f"docs/{name}.svg"
        with open(path, "w") as f:
            f.write(svg)
        print(f"Generated: {path}")
