#!/usr/bin/env python3
"""Generate SVG screenshots for README using Rich's export_svg."""

import sys
sys.path.insert(0, ".")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
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
        # color last commit
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


if __name__ == "__main__":
    for name, fn in [("dashboard", gen_dashboard), ("health", gen_health), ("activity", gen_activity)]:
        svg = fn()
        path = f"docs/{name}.svg"
        with open(path, "w") as f:
            f.write(svg)
        print(f"Generated: {path}")
