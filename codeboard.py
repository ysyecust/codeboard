#!/usr/bin/env python3
"""CodeBoard - 本地代码仓库仪表盘"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

DEFAULT_CODE_DIR = Path.home() / "Code"
# 额外单独纳管的仓库路径（不整目录扫描，只加特定仓库）
EXTRA_REPOS = [
    Path.home() / "Documents" / "Code" / "EO",
    Path.home() / "Documents" / "Code" / "SimonaSolver",
]
OBSIDIAN_VAULT = Path.home() / "Documents" / "Obsidian Vault"
GITNEXUS_BIN = str(Path.home() / ".nvm/versions/node/v22.15.1/bin/gitnexus")

LANG_MAP = {
    ".py": "Python", ".pyx": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "React",
    ".c": "C", ".h": "C/C++",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".jl": "Julia",
    ".r": "R", ".R": "R",
    ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "CSS", ".less": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir",
    ".zig": "Zig",
    ".nim": "Nim",
    ".f90": "Fortran", ".f95": "Fortran", ".f03": "Fortran",
    ".m": "MATLAB/ObjC",
    ".tex": "LaTeX",
    ".md": "Markdown",
    ".sql": "SQL",
    ".proto": "Protobuf",
}

IGNORE_EXTS = {
    ".json", ".yaml", ".yml", ".toml", ".xml", ".lock", ".sum",
    ".txt", ".csv", ".log", ".gitignore", ".dockerignore",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".tar", ".gz",
    ".map", ".min.js", ".min.css",
}


def run_git(repo_path: Path, *args: str, timeout: int = 10) -> str:
    """执行 git 命令并返回 stdout"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path)] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def relative_time(dt: datetime) -> str:
    """将 datetime 转换为中文相对时间"""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return "刚刚"
    if seconds < 60:
        return f"{seconds}秒前"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}小时前"
    days = hours // 24
    if days < 30:
        return f"{days}天前"
    months = days // 30
    if months < 12:
        return f"{months}月前"
    years = days // 365
    return f"{years}年前"


def detect_remote_type(url: str) -> str:
    """从 remote URL 判断类型"""
    if not url:
        return "none"
    url_lower = url.lower()
    if "github.com" in url_lower:
        return "github"
    if "gitlab" in url_lower:
        return "gitlab"
    if "gitee.com" in url_lower:
        return "gitee"
    if "bitbucket" in url_lower:
        return "bitbucket"
    return "other"


def detect_language(repo_path: Path) -> str:
    """检测仓库主要语言 (快速版)"""
    output = run_git(repo_path, "ls-files")
    if not output:
        return "-"
    counter = Counter()
    for f in output.split("\n"):
        ext = Path(f).suffix.lower()
        if ext in IGNORE_EXTS or not ext:
            continue
        lang = LANG_MAP.get(ext)
        if lang:
            counter[lang] += 1
    if not counter:
        return "-"
    return counter.most_common(1)[0][0]


def detect_language_detail(repo_path: Path) -> list[tuple[str, int]]:
    """检测仓库语言占比 (详细版)"""
    output = run_git(repo_path, "ls-files")
    if not output:
        return []
    counter = Counter()
    for f in output.split("\n"):
        ext = Path(f).suffix.lower()
        if ext in IGNORE_EXTS or not ext:
            continue
        lang = LANG_MAP.get(ext)
        if lang:
            counter[lang] += 1
    return counter.most_common()


SCAN_SCRIPT_BASE = r"""
cd "$1" || exit 1
echo "%%BRANCH%%$(git branch --show-current 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)"
echo "%%LOG%%$(git log -1 --format='%aI|%s' 2>/dev/null)"
echo "%%DIRTY%%$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "%%COUNT%%$(git rev-list --count HEAD 2>/dev/null)"
echo "%%REMOTE%%$(git remote get-url origin 2>/dev/null)"
echo "%%AB%%$(git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null)"
"""

SCAN_SCRIPT_FULL = SCAN_SCRIPT_BASE + r"""
echo "%%LANG%%$(git ls-files 2>/dev/null)"
"""


def scan_repo(repo_path: Path, full: bool = False) -> dict | None:
    """扫描单个仓库 (单次 shell 调用)"""
    if not (repo_path / ".git").is_dir():
        return None

    name = repo_path.name
    script = SCAN_SCRIPT_FULL if full else SCAN_SCRIPT_BASE
    try:
        r = subprocess.run(
            ["sh", "-c", script, "--", str(repo_path)],
            capture_output=True, text=True, timeout=15,
        )
        output = r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    def extract(tag: str) -> str:
        marker = f"%%{tag}%%"
        for line in output.split("\n"):
            if line.startswith(marker):
                return line[len(marker):]
        return ""

    branch = extract("BRANCH") or "?"

    log_line = extract("LOG")
    last_time = None
    last_msg = ""
    if log_line and "|" in log_line:
        parts = log_line.split("|", 1)
        last_msg = parts[1]
        try:
            last_time = datetime.fromisoformat(parts[0])
        except ValueError:
            pass

    dirty_str = extract("DIRTY")
    dirty_count = int(dirty_str) if dirty_str.isdigit() else 0

    commit_str = extract("COUNT")
    commit_count = int(commit_str) if commit_str.isdigit() else 0

    remote_url = extract("REMOTE")
    remote_type = detect_remote_type(remote_url)

    ahead, behind = 0, 0
    ab = extract("AB")
    if ab and "\t" in ab:
        parts = ab.split("\t")
        ahead = int(parts[0]) if parts[0].isdigit() else 0
        behind = int(parts[1]) if parts[1].isdigit() else 0

    lang = ""
    if full:
        # 语言检测：复用已获取的 ls-files 输出
        lang_marker = "%%LANG%%"
        lang_output = ""
        idx = output.find(lang_marker)
        if idx >= 0:
            lang_output = output[idx + len(lang_marker):]
        if lang_output:
            counter = Counter()
            for f in lang_output.split("\n"):
                ext = Path(f).suffix.lower()
                if ext in IGNORE_EXTS or not ext:
                    continue
                l = LANG_MAP.get(ext)
                if l:
                    counter[l] += 1
            lang = counter.most_common(1)[0][0] if counter else "-"
        else:
            lang = "-"

    info = {
        "name": name,
        "path": str(repo_path),
        "branch": branch,
        "last_time": last_time,
        "last_time_rel": relative_time(last_time) if last_time else "无提交",
        "last_time_ts": last_time.timestamp() if last_time else 0,
        "last_msg": last_msg,
        "dirty": dirty_count,
        "commits": commit_count,
        "remote_url": remote_url,
        "remote_type": remote_type,
        "ahead": ahead,
        "behind": behind,
        "lang": lang,
    }
    return info


def list_git_repos(code_dir: Path, filter_kw: str = "") -> list[Path]:
    """列出所有 git 仓库路径（含 EXTRA_REPOS）"""
    repos = [d for d in code_dir.iterdir() if d.is_dir() and (d / ".git").is_dir()]
    for extra in EXTRA_REPOS:
        if extra.is_dir() and (extra / ".git").is_dir() and extra.parent != code_dir:
            repos.append(extra)
    repos.sort(key=lambda p: p.name.lower())
    if filter_kw:
        repos = [r for r in repos if filter_kw.lower() in r.name.lower()]
    return repos


def scan_all(code_dir: Path, full: bool = True, filter_kw: str = "") -> list[dict]:
    """并行扫描所有仓库"""
    repos = list_git_repos(code_dir, filter_kw)

    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(scan_repo, r, full): r for r in repos}
        for future in as_completed(futures):
            info = future.result()
            if info:
                results.append(info)
    return results


def sort_repos(repos: list[dict], sort_key: str = "activity") -> list[dict]:
    """排序仓库列表"""
    if sort_key == "name":
        return sorted(repos, key=lambda r: r["name"].lower())
    if sort_key == "commits":
        return sorted(repos, key=lambda r: r["commits"], reverse=True)
    if sort_key == "changes":
        return sorted(repos, key=lambda r: r["dirty"], reverse=True)
    # default: activity (最近活跃在前)
    return sorted(repos, key=lambda r: r["last_time_ts"], reverse=True)


def cmd_dashboard(args):
    """主仪表盘"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=True, filter_kw=args.filter)
    repos = sort_repos(repos, args.sort)

    if args.json:
        for r in repos:
            r.pop("last_time", None)
        print(json.dumps(repos, ensure_ascii=False, indent=2))
        return

    table = Table(box=box.ROUNDED, show_lines=False, padding=(0, 1))
    table.add_column("名称", style="bold cyan", no_wrap=True, max_width=20)
    table.add_column("分支", style="magenta", no_wrap=True, max_width=15)
    table.add_column("最后提交", no_wrap=True, max_width=10)
    table.add_column("状态", no_wrap=True, justify="center")
    table.add_column("语言", no_wrap=True, max_width=12)
    table.add_column("提交数", justify="right")
    table.add_column("远程", no_wrap=True)

    for r in repos:
        # 最后提交时间着色
        rel = r["last_time_rel"]
        if r["last_time_ts"] == 0:
            time_text = Text("无提交", style="dim")
        elif "小时" in rel or "分钟" in rel or "秒" in rel:
            time_text = Text(rel, style="green")
        elif "天" in rel:
            days = int(rel.replace("天前", ""))
            time_text = Text(rel, style="green" if days <= 7 else "yellow")
        else:
            time_text = Text(rel, style="dim red")

        # 状态
        if r["dirty"] > 0:
            status = Text(f"●{r['dirty']}", style="yellow")
        else:
            status = Text("✓", style="green")

        # 远程
        rt = r["remote_type"]
        if rt == "github":
            remote_text = Text("github", style="bright_white")
        elif rt == "gitlab":
            remote_text = Text("gitlab", style="bright_red")
        elif rt == "gitee":
            remote_text = Text("gitee", style="bright_red")
        elif rt == "none":
            remote_text = Text("local", style="dim")
        else:
            remote_text = Text(rt, style="dim")

        # ahead/behind 标记
        if r["ahead"] > 0 or r["behind"] > 0:
            markers = []
            if r["ahead"] > 0:
                markers.append(f"↑{r['ahead']}")
            if r["behind"] > 0:
                markers.append(f"↓{r['behind']}")
            remote_text.append(f" {' '.join(markers)}", style="yellow")

        # 非默认目录的仓库加路径标注
        display_name = Text(r["name"], style="bold cyan")
        if Path(r["path"]).parent != code_dir:
            short_parent = str(Path(r["path"]).parent).replace(str(Path.home()), "~")
            display_name.append(f" ({short_parent})", style="dim")

        table.add_row(
            display_name,
            r["branch"],
            time_text,
            status,
            r["lang"] or "-",
            str(r["commits"]),
            remote_text,
        )

    title = f"CodeBoard ── {code_dir} ── {len(repos)} repos"
    panel = Panel(table, title=title, subtitle="● = 未提交变更  ✓ = 干净", border_style="blue")
    console.print(panel)


def cmd_activity(args):
    """跨仓库活动时间线"""
    code_dir = Path(args.path).expanduser()
    limit = args.limit

    repos = list_git_repos(code_dir, filter_kw=args.filter)

    all_commits = []

    def get_recent_commits(repo_path: Path):
        output = run_git(repo_path, "log", "--all", f"--max-count={limit}", "--format=%aI|%an|%s")
        if not output:
            return []
        entries = []
        for line in output.split("\n"):
            if "|" not in line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            try:
                dt = datetime.fromisoformat(parts[0])
            except ValueError:
                continue
            entries.append({
                "time": dt,
                "time_ts": dt.timestamp(),
                "time_rel": relative_time(dt),
                "author": parts[1],
                "message": parts[2],
                "repo": repo_path.name,
            })
        return entries

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(get_recent_commits, r): r for r in repos}
        for future in as_completed(futures):
            all_commits.extend(future.result())

    all_commits.sort(key=lambda c: c["time_ts"], reverse=True)
    all_commits = all_commits[:limit]

    if args.json:
        for c in all_commits:
            c.pop("time", None)
        print(json.dumps(all_commits, ensure_ascii=False, indent=2))
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("时间", style="dim", no_wrap=True, max_width=10)
    table.add_column("仓库", style="bold cyan", no_wrap=True, max_width=20)
    table.add_column("作者", style="magenta", no_wrap=True, max_width=12)
    table.add_column("提交信息", max_width=60)

    for c in all_commits:
        msg = c["message"]
        if len(msg) > 60:
            msg = msg[:57] + "..."
        # 根据提交类型着色
        if msg.startswith("feat"):
            msg_text = Text(msg, style="green")
        elif msg.startswith("fix"):
            msg_text = Text(msg, style="yellow")
        elif msg.startswith("refactor") or msg.startswith("chore"):
            msg_text = Text(msg, style="dim")
        else:
            msg_text = Text(msg)

        table.add_row(c["time_rel"], c["repo"], c["author"], msg_text)

    panel = Panel(table, title=f"Recent Activity ── {len(all_commits)} commits", border_style="blue")
    console.print(panel)


def cmd_health(args):
    """健康检查报告"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)

    if args.json:
        for r in repos:
            r.pop("last_time", None)
        print(json.dumps(repos, ensure_ascii=False, indent=2))
        return

    # 分类
    dirty_repos = [r for r in repos if r["dirty"] > 0]
    ahead_repos = [r for r in repos if r["ahead"] > 0]
    behind_repos = [r for r in repos if r["behind"] > 0]
    no_remote = [r for r in repos if r["remote_type"] == "none"]
    now_ts = datetime.now(timezone.utc).timestamp()
    inactive = [r for r in repos if r["last_time_ts"] > 0 and (now_ts - r["last_time_ts"]) > 30 * 86400]
    inactive.sort(key=lambda r: r["last_time_ts"])
    clean = [r for r in repos if r["dirty"] == 0 and r["ahead"] == 0 and r["behind"] == 0
             and r["remote_type"] != "none" and (now_ts - r["last_time_ts"]) <= 30 * 86400]

    lines = []

    if dirty_repos:
        dirty_repos.sort(key=lambda r: r["dirty"], reverse=True)
        items = " | ".join(f"{r['name']} ({r['dirty']})" for r in dirty_repos)
        lines.append(Text.assemble(
            ("  ⚠ 未提交变更", "bold yellow"),
            (f" ({len(dirty_repos)} repos)\n", "yellow"),
            (f"    {items}\n", ""),
        ))

    if ahead_repos:
        items = " | ".join(f"{r['name']} (↑{r['ahead']})" for r in ahead_repos)
        lines.append(Text.assemble(
            ("  ⚠ 未推送提交", "bold yellow"),
            (f" ({len(ahead_repos)} repos)\n", "yellow"),
            (f"    {items}\n", ""),
        ))

    if behind_repos:
        items = " | ".join(f"{r['name']} (↓{r['behind']})" for r in behind_repos)
        lines.append(Text.assemble(
            ("  ⚠ 落后远程", "bold red"),
            (f" ({len(behind_repos)} repos)\n", "red"),
            (f"    {items}\n", ""),
        ))

    if no_remote:
        items = " | ".join(r["name"] for r in no_remote)
        lines.append(Text.assemble(
            ("  ○ 无远程仓库", "bold dim"),
            (f" ({len(no_remote)} repos)\n", "dim"),
            (f"    {items}\n", ""),
        ))

    if inactive:
        items = " | ".join(f"{r['name']} ({r['last_time_rel']})" for r in inactive)
        lines.append(Text.assemble(
            ("  ○ 长期未活跃 >30天", "bold dim"),
            (f" ({len(inactive)} repos)\n", "dim"),
            (f"    {items}\n", ""),
        ))

    if clean:
        lines.append(Text.assemble(
            ("  ✓ 一切正常", "bold green"),
            (f" ({len(clean)} repos)\n", "green"),
        ))

    content = Text()
    for line in lines:
        content.append_text(line)
        content.append("\n")

    panel = Panel(content, title="Health Report", border_style="blue")
    console.print(panel)


def cmd_detail(args):
    """单个仓库详情"""
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return
    repo_name = repo_path.name

    info = scan_repo(repo_path, full=True)
    if not info:
        console.print(f"[red]无法扫描: {repo_name}[/red]")
        return

    if args.json:
        info.pop("last_time", None)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    # 额外详细信息
    branches = run_git(repo_path, "branch", "--list").split("\n")
    branches = [b.strip().lstrip("* ") for b in branches if b.strip()]
    branch_count = len(branches)

    tags = run_git(repo_path, "tag", "--list").split("\n")
    tags = [t for t in tags if t.strip()]
    tag_count = len(tags)
    latest_tag = tags[-1] if tags else "无"

    contributors_out = run_git(repo_path, "shortlog", "-sn", "HEAD")
    contributors = []
    for line in contributors_out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            contributors.append((parts[1], int(parts[0].strip())))

    lang_detail = detect_language_detail(repo_path)
    total_files = sum(c for _, c in lang_detail)

    # 本周/本月提交数
    week_commits = run_git(repo_path, "rev-list", "--count", "--since=7 days ago", "HEAD")
    month_commits = run_git(repo_path, "rev-list", "--count", "--since=30 days ago", "HEAD")
    week_n = int(week_commits) if week_commits.isdigit() else 0
    month_n = int(month_commits) if month_commits.isdigit() else 0

    # 最近提交
    recent_log = run_git(repo_path, "log", "-10", "--format=%aI|%s")
    recent_commits = []
    for line in recent_log.split("\n"):
        if "|" not in line:
            continue
        parts = line.split("|", 1)
        try:
            dt = datetime.fromisoformat(parts[0])
            recent_commits.append((relative_time(dt), parts[1]))
        except ValueError:
            pass

    # 状态详情
    staged = 0
    unstaged = 0
    untracked = 0
    status_lines = run_git(repo_path, "status", "--porcelain")
    for sl in status_lines.split("\n"):
        if not sl:
            continue
        if sl.startswith("??"):
            untracked += 1
        elif sl[0] != " ":
            staged += 1
        else:
            unstaged += 1

    # 构建输出
    lines = []
    lines.append(f"  [dim]路径:[/dim]     {repo_path}")
    lines.append(f"  [dim]远程:[/dim]     {info['remote_url'] or '无'}")
    branch_extra = f" (+ {branch_count - 1} branches)" if branch_count > 1 else ""
    lines.append(f"  [dim]分支:[/dim]     [magenta]{info['branch']}[/magenta]{branch_extra}")
    lines.append(f"  [dim]标签:[/dim]     {tag_count} tags (latest: {latest_tag})")
    lines.append(f"  [dim]提交:[/dim]     {info['commits']} commits")

    if contributors:
        contribs_str = ", ".join(f"{name}({n})" for name, n in contributors[:5])
        lines.append(f"  [dim]贡献者:[/dim]   {len(contributors)} ({contribs_str})")

    if lang_detail:
        lang_str = " | ".join(
            f"{lang} {count * 100 // total_files}%" for lang, count in lang_detail[:5]
        )
        lines.append(f"  [dim]语言:[/dim]     {lang_str}")

    status_parts = []
    if unstaged > 0:
        status_parts.append(f"{unstaged} modified")
    if staged > 0:
        status_parts.append(f"{staged} staged")
    if untracked > 0:
        status_parts.append(f"{untracked} untracked")
    if not status_parts:
        status_parts.append("[green]clean[/green]")
    lines.append(f"  [dim]状态:[/dim]     {', '.join(status_parts)}")

    lines.append("")
    lines.append("  [bold]最近提交:[/bold]")
    for rel, msg in recent_commits:
        if len(msg) > 55:
            msg = msg[:52] + "..."
        lines.append(f"   [dim]{rel:>8}[/dim]  {msg}")

    lines.append("")
    # 活跃度条
    max_bar = 12
    bar_filled = min(max_bar, month_n)
    bar = "█" * bar_filled + "░" * (max_bar - bar_filled)
    lines.append(f"  [dim]活跃度:[/dim]   {bar} 本周 {week_n} | 本月 {month_n}")

    content = "\n".join(lines)
    panel = Panel(content, title=f"[bold]{repo_name}[/bold]", border_style="blue")
    console.print(panel)


def cmd_stats(args):
    """汇总统计"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=True, filter_kw=args.filter)

    if args.json:
        for r in repos:
            r.pop("last_time", None)
        print(json.dumps(repos, ensure_ascii=False, indent=2))
        return

    total = len(repos)
    now_ts = datetime.now(timezone.utc).timestamp()
    active_30 = sum(1 for r in repos if (now_ts - r["last_time_ts"]) <= 30 * 86400 and r["last_time_ts"] > 0)
    has_remote = sum(1 for r in repos if r["remote_type"] != "none")
    total_commits = sum(r["commits"] for r in repos)

    # 本月提交 (近似: 取每个仓库本月提交数)
    month_commits = 0
    def get_month_commits(repo_path):
        r = run_git(Path(repo_path), "rev-list", "--count", "--since=30 days ago", "HEAD")
        return int(r) if r.isdigit() else 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(get_month_commits, r["path"]) for r in repos]
        for f in as_completed(futures):
            month_commits += f.result()

    # 本周提交
    week_commits = 0
    def get_week_commits(repo_path):
        r = run_git(Path(repo_path), "rev-list", "--count", "--since=7 days ago", "HEAD")
        return int(r) if r.isdigit() else 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures_w = {pool.submit(get_week_commits, r["path"]): r for r in repos}
        week_per_repo = {}
        for f in as_completed(futures_w):
            repo = futures_w[f]
            n = f.result()
            week_commits += n
            week_per_repo[repo["name"]] = n

    lines = []
    lines.append(f"  [bold]总仓库:[/bold] {total}  |  [bold]活跃(30天):[/bold] {active_30}  |  [bold]有远程:[/bold] {has_remote}")
    lines.append(f"  [bold]总提交:[/bold] {total_commits:,}  |  [bold]本月:[/bold] {month_commits}  |  [bold]本周:[/bold] {week_commits}")
    lines.append("")

    # 语言分布
    lang_counter = Counter()
    for r in repos:
        if r["lang"] and r["lang"] != "-":
            lang_counter[r["lang"]] += 1

    if lang_counter:
        lines.append("  [bold]语言分布:[/bold]")
        max_count = lang_counter.most_common(1)[0][1]
        bar_width = 20
        for lang, count in lang_counter.most_common(10):
            bar_len = max(1, count * bar_width // max_count)
            bar = "█" * bar_len + "░" * (bar_width - bar_len)
            lines.append(f"   {lang:<12} {bar} {count:>2} repos")
        lines.append("")

    # 本周活跃 Top
    top_week = sorted(week_per_repo.items(), key=lambda x: x[1], reverse=True)
    top_week = [(name, n) for name, n in top_week if n > 0][:8]
    if top_week:
        lines.append("  [bold]本周活跃 Top:[/bold]")
        items = " | ".join(f"[cyan]{name}[/cyan]({n})" for name, n in top_week)
        lines.append(f"   {items}")
        lines.append("")

    # 远程分布
    remote_counter = Counter(r["remote_type"] for r in repos)
    if remote_counter:
        lines.append("  [bold]远程分布:[/bold]")
        items = " | ".join(f"{k}: {v}" for k, v in remote_counter.most_common())
        lines.append(f"   {items}")

    content = "\n".join(lines)
    panel = Panel(content, title="Statistics", border_style="blue")
    console.print(panel)


def find_repo(code_dir: Path, name: str) -> Path | None:
    """按名称查找仓库，支持模糊匹配（含 EXTRA_REPOS）"""
    # 支持直接传路径
    direct = Path(name).expanduser()
    if direct.is_absolute() and (direct / ".git").is_dir():
        return direct
    all_repos = list_git_repos(code_dir)
    # 精确匹配
    for r in all_repos:
        if r.name == name:
            return r
    # 模糊匹配
    candidates = [r for r in all_repos if name.lower() in r.name.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        hints = [f"{c.name} ({c.parent})" for c in candidates]
        console.print(f"[yellow]多个匹配: {', '.join(hints)}[/yellow]")
        console.print("[dim]提示: 用完整路径区分，如 cb detail ~/Documents/Code/EO[/dim]")
        return None
    console.print(f"[red]未找到仓库: {name}[/red]")
    return None


def require_lazygit() -> str | None:
    """检查 lazygit 是否可用，返回路径"""
    path = shutil.which("lazygit")
    if not path:
        console.print("[red]未安装 lazygit[/red]  brew install lazygit")
    return path


def require_gitnexus() -> str | None:
    """检查 gitnexus 是否可用，返回路径"""
    path = shutil.which("gitnexus") or (GITNEXUS_BIN if Path(GITNEXUS_BIN).is_file() else None)
    if not path:
        console.print("[red]未找到 gitnexus[/red]  npm install -g gitnexus")
        console.print(f"[dim]期望路径: {GITNEXUS_BIN}[/dim]")
    return path


def is_graph_indexed(repo_path: Path) -> bool:
    """检查仓库是否已建立 GitNexus 图索引"""
    return (repo_path / ".gitnexus").is_dir()


def run_gitnexus(gn: str, subcmd: str, *args, timeout: int = 60) -> tuple[bool, str]:
    """调用 gitnexus 并返回 (成功, 输出) — gitnexus 把 JSON 输出到 stderr"""
    try:
        r = subprocess.run(
            [gn, subcmd, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        # gitnexus 将结构化输出写入 stderr
        output = r.stderr.strip() or r.stdout.strip()
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, ""
    except Exception as e:
        return False, str(e)


def cmd_open(args):
    """用 lazygit 打开指定仓库"""
    lg = require_lazygit()
    if not lg:
        return
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return

    panel = getattr(args, "panel", None)
    cmd = [lg, "--path", str(repo_path)]
    if panel:
        cmd.append(panel)
    console.print(f"[dim]lazygit → {repo_path.name}[/dim]")
    os.execvp(lg, cmd)


def cmd_dirty(args):
    """列出有未提交变更的仓库，选择后用 lazygit 打开"""
    lg = require_lazygit()
    if not lg:
        return
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    dirty = sorted([r for r in repos if r["dirty"] > 0], key=lambda r: r["dirty"], reverse=True)

    if not dirty:
        console.print("[green]所有仓库都是干净的[/green]")
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("仓库", style="bold cyan", no_wrap=True)
    table.add_column("变更", style="yellow", justify="right")
    table.add_column("分支", style="magenta")
    table.add_column("最后提交", style="dim")

    for i, r in enumerate(dirty, 1):
        table.add_row(str(i), r["name"], str(r["dirty"]), r["branch"], r["last_time_rel"])

    panel = Panel(table, title=f"有未提交变更的仓库 ({len(dirty)})", border_style="yellow")
    console.print(panel)
    console.print("[dim]输入序号用 lazygit 打开，直接回车退出[/dim]")

    try:
        choice = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not choice:
        return
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(dirty):
        console.print("[red]无效序号[/red]")
        return

    repo = dirty[int(choice) - 1]
    console.print(f"[dim]lazygit → {repo['name']}[/dim]")
    os.execvp(lg, [lg, "--path", repo["path"]])


def cmd_each(args):
    """逐个用 lazygit 打开有变更的仓库"""
    lg = require_lazygit()
    if not lg:
        return
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    dirty = sorted([r for r in repos if r["dirty"] > 0], key=lambda r: r["dirty"], reverse=True)

    if not dirty:
        console.print("[green]所有仓库都是干净的[/green]")
        return

    console.print(f"[bold]逐个处理 {len(dirty)} 个有变更的仓库[/bold]")
    console.print("[dim]每个仓库关闭 lazygit 后自动跳到下一个，Ctrl+C 退出[/dim]\n")

    for i, r in enumerate(dirty, 1):
        console.print(f"[cyan][{i}/{len(dirty)}][/cyan] {r['name']} [yellow](●{r['dirty']})[/yellow]")
        try:
            subprocess.run([lg, "--path", r["path"]])
        except KeyboardInterrupt:
            console.print("\n[dim]已中断[/dim]")
            return
    console.print("\n[green]全部处理完毕[/green]")


def cmd_pull(args):
    """批量 git pull"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    targets = [r for r in repos if r["remote_type"] != "none"]

    if not targets:
        if args.json:
            print(json.dumps({"ok": [], "skip": [], "fail": []}, indent=2))
        else:
            console.print("[dim]没有配置远程仓库的项目[/dim]")
        return

    if not args.json:
        console.print(f"[bold]准备 pull {len(targets)} 个有远程的仓库[/bold]\n")

    results = {"ok": [], "skip": [], "fail": []}

    def do_pull(repo_info):
        path = Path(repo_info["path"])
        try:
            r = subprocess.run(
                ["git", "-C", str(path), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                out = r.stdout.strip()
                if "Already up to date" in out or "已经是最新" in out:
                    return ("skip", repo_info, "")
                return ("ok", repo_info, out.split("\n")[-1])
            return ("fail", repo_info, r.stderr.strip().split("\n")[0])
        except subprocess.TimeoutExpired:
            return ("fail", repo_info, "timeout")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(do_pull, r): r for r in targets}
        for f in as_completed(futures):
            status, repo_info, msg = f.result()
            results[status].append((repo_info, msg))

    if args.json:
        out = {k: [{"name": r["name"], "message": m} for r, m in v] for k, v in results.items()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if results["ok"]:
        console.print(f"[green]  ✓ 已更新 ({len(results['ok'])})[/green]")
        for r, msg in sorted(results["ok"], key=lambda x: x[0]["name"]):
            console.print(f"    [cyan]{r['name']}[/cyan] {msg}")

    if results["fail"]:
        console.print(f"[red]  ✗ 失败 ({len(results['fail'])})[/red]")
        for r, msg in sorted(results["fail"], key=lambda x: x[0]["name"]):
            console.print(f"    [cyan]{r['name']}[/cyan] [dim]{msg}[/dim]")

    skipped = len(results["skip"])
    if skipped:
        console.print(f"[dim]  ─ 已是最新 ({skipped})[/dim]")


def cmd_push(args):
    """推送所有有 ahead 提交的仓库"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    targets = [r for r in repos if r["ahead"] > 0]

    if not targets:
        console.print("[green]没有需要推送的仓库[/green]")
        return

    targets.sort(key=lambda r: r["ahead"], reverse=True)

    if args.json:
        print(json.dumps([{"name": r["name"], "ahead": r["ahead"]} for r in targets], ensure_ascii=False, indent=2))
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("仓库", style="bold cyan")
    table.add_column("分支", style="magenta")
    table.add_column("未推送", style="yellow", justify="right")
    table.add_column("远程", style="dim")

    for r in targets:
        table.add_row(r["name"], r["branch"], f"↑{r['ahead']}", r["remote_type"])

    console.print(table)
    console.print(f"\n[bold]确认推送以上 {len(targets)} 个仓库? [y/N][/bold]")
    try:
        choice = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice not in ("y", "yes"):
        console.print("[dim]已取消[/dim]")
        return

    for r in targets:
        path = Path(r["path"])
        result = subprocess.run(
            ["git", "-C", str(path), "push"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            console.print(f"  [green]✓[/green] {r['name']}")
        else:
            err = result.stderr.strip().split("\n")[0]
            console.print(f"  [red]✗[/red] {r['name']} [dim]{err}[/dim]")

    console.print("\n[green]推送完成[/green]")


def cmd_commit(args):
    """快速 commit 指定仓库"""
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return

    message = args.message
    if not message:
        console.print("[red]缺少提交信息，请用 -m 指定[/red]")
        return

    # 先看看有什么变更
    status = run_git(repo_path, "status", "--porcelain")
    if not status:
        console.print(f"[green]{repo_path.name}: 工作区干净，无需提交[/green]")
        return

    lines = status.split("\n")
    console.print(f"[bold]{repo_path.name}[/bold] — {len(lines)} 个变更文件:")
    for line in lines[:10]:
        flag = line[:2]
        fname = line[3:]
        if flag.strip() == "??":
            console.print(f"  [green]+ {fname}[/green]")
        elif "D" in flag:
            console.print(f"  [red]- {fname}[/red]")
        else:
            console.print(f"  [yellow]~ {fname}[/yellow]")
    if len(lines) > 10:
        console.print(f"  [dim]... 还有 {len(lines) - 10} 个文件[/dim]")

    if not args.yes:
        console.print(f'\n[bold]提交信息:[/bold] "{message}"')
        console.print("[bold]确认 git add -A && commit? [y/N][/bold]")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice not in ("y", "yes"):
            console.print("[dim]已取消[/dim]")
            return

    # git add -A && git commit
    run_git(repo_path, "add", "-A")
    result = subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", message],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        console.print(f"[green]✓ 已提交[/green]")
    else:
        console.print(f"[red]✗ 提交失败:[/red] {result.stderr.strip()}")


def cmd_stash(args):
    """快速 stash 指定仓库"""
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return

    action = getattr(args, "action", "push") or "push"

    if action == "push":
        status = run_git(repo_path, "status", "--porcelain")
        if not status:
            console.print(f"[green]{repo_path.name}: 工作区干净，无需 stash[/green]")
            return
        dirty_n = len(status.split("\n"))
        msg = getattr(args, "message", None)
        cmd_args = ["stash", "push", "--include-untracked"]
        if msg:
            cmd_args.extend(["-m", msg])
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + cmd_args,
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ {repo_path.name}: stash 了 {dirty_n} 个变更[/green]")
        else:
            console.print(f"[red]✗ stash 失败:[/red] {result.stderr.strip()}")

    elif action == "pop":
        result = subprocess.run(
            ["git", "-C", str(repo_path), "stash", "pop"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ {repo_path.name}: stash pop 成功[/green]")
        else:
            console.print(f"[red]✗ stash pop 失败:[/red] {result.stderr.strip()}")

    elif action == "list":
        out = run_git(repo_path, "stash", "list")
        if out:
            console.print(f"[bold]{repo_path.name} stash 列表:[/bold]")
            for line in out.split("\n"):
                console.print(f"  {line}")
        else:
            console.print(f"[dim]{repo_path.name}: 没有 stash[/dim]")


def cmd_grep(args):
    """跨仓库代码搜索"""
    code_dir = Path(args.path).expanduser()
    pattern = args.pattern
    repos = list_git_repos(code_dir, filter_kw=args.filter)

    all_results = []

    def search_repo(repo_path: Path):
        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "grep", "-n", "--color=never",
                 "-I",  # skip binary
                 "-l" if args.json else "-n",
                 pattern],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                return (repo_path.name, r.stdout.strip())
        except subprocess.TimeoutExpired:
            pass
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(search_repo, r): r for r in repos}
        for f in as_completed(futures):
            result = f.result()
            if result:
                all_results.append(result)

    all_results.sort(key=lambda x: x[0].lower())

    if not all_results:
        console.print(f"[dim]未找到匹配: {pattern}[/dim]")
        return

    if args.json:
        out = {}
        for repo_name, files in all_results:
            out[repo_name] = files.split("\n")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    total_matches = 0
    for repo_name, output in all_results:
        lines = output.split("\n")
        total_matches += len(lines)
        console.print(f"\n[bold cyan]{repo_name}[/bold cyan] [dim]({len(lines)} matches)[/dim]")
        shown = lines[:8]
        for line in shown:
            # line format: "file:line:content"
            if ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    console.print(f"  [dim]{parts[0]}:{parts[1]}[/dim] {parts[2].strip()}")
                else:
                    console.print(f"  {line}")
            else:
                console.print(f"  {line}")
        if len(lines) > 8:
            console.print(f"  [dim]... 还有 {len(lines) - 8} 条[/dim]")

    console.print(f"\n[dim]共 {len(all_results)} 个仓库, {total_matches} 条匹配[/dim]")


# ---------------------------------------------------------------------------
# graph 命令 - GitNexus 代码图谱分析
# ---------------------------------------------------------------------------

def _parse_md_table(raw: str) -> list[list[str]]:
    """解析 gitnexus cypher 返回的 markdown 表格 (JSON 包裹), 返回数据行 (跳过表头和分隔行)"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    md = data.get("markdown", "")
    rows = []
    header_skipped = False
    for line in md.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line:
            header_skipped = True
            continue
        if not header_skipped:
            # 第一行是表头，跳过
            header_skipped = False  # 等 --- 分隔行来标记
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells:
            rows.append(cells)
    return rows


def _graph_require(args) -> tuple[str, Path, str] | None:
    """graph 子命令公共前置: 返回 (gitnexus路径, 仓库路径, 仓库名) 或 None"""
    gn = require_gitnexus()
    if not gn:
        return None
    code_dir = Path(args.path).expanduser()
    repo_name = getattr(args, "repo", None)
    if not repo_name:
        console.print("[red]请指定仓库名称[/red]")
        return None
    repo_path = find_repo(code_dir, repo_name)
    if not repo_path:
        return None
    return gn, repo_path, repo_path.name


def cmd_graph_index(args):
    """索引仓库到 GitNexus 知识图谱"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if is_graph_indexed(repo_path):
        console.print(f"[yellow]⟳ {repo_name} 已有索引，将重新构建[/yellow]")

    # 检测语言，对 C++ 给出警告
    info = scan_repo(repo_path, full=True)
    if info and info.get("lang") in ("C++", "C", "C/C++"):
        console.print("[yellow]⚠ C/C++ 项目索引可能耗时较长或不稳定[/yellow]")

    console.print(f"[bold]索引: {repo_name}[/bold] → {repo_path}\n")
    try:
        # 直接输出到终端，让用户看到进度
        r = subprocess.run([gn, "index", str(repo_path)], timeout=180)
        if r.returncode == 0:
            console.print(f"\n[green]✓ 索引完成: {repo_name}[/green]")
        else:
            console.print(f"\n[red]✗ 索引失败 (exit {r.returncode})[/red]")
    except subprocess.TimeoutExpired:
        console.print("\n[red]✗ 索引超时 (>180s)[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")


def cmd_graph_overview(args):
    """显示仓库图谱概览"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]尚未建立图索引，请先运行: cb graph index {repo_name}[/yellow]")
        return

    # 索引时间
    gn_dir = repo_path / ".gitnexus"
    try:
        mtime = datetime.fromtimestamp(gn_dir.stat().st_mtime)
        idx_time = relative_time(mtime)
    except Exception:
        idx_time = "未知"

    # 查询节点统计
    ok1, out1 = run_gitnexus(gn, "cypher",
        "MATCH (n) RETURN labels(n) AS type, count(*) AS cnt ORDER BY cnt DESC",
        "--repo", repo_name)

    # 查询边统计
    ok2, out2 = run_gitnexus(gn, "cypher",
        "MATCH ()-[r:CodeRelation]->() RETURN r.type AS edgeType, count(*) AS cnt ORDER BY cnt DESC",
        "--repo", repo_name)

    # 查询社区数
    ok3, out3 = run_gitnexus(gn, "cypher",
        "MATCH (c:Community) RETURN count(*) AS n",
        "--repo", repo_name)

    # 查询高出度函数 (调用最多的函数)
    ok4, out4 = run_gitnexus(gn, "cypher",
        "MATCH (a:Function)-[r:CodeRelation {type: 'CALLS'}]->(b) "
        "RETURN a.name AS fn, a.filePath AS file, count(*) AS calls "
        "ORDER BY calls DESC LIMIT 10",
        "--repo", repo_name)

    # ── 构建输出 ──
    parts = []
    parts.append(f"[dim]索引时间: {idx_time}[/dim]\n")

    # 节点统计表
    if ok1:
        rows = _parse_md_table(out1)
        if rows:
            tbl = Table(title="节点统计", box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column("类型", style="cyan", no_wrap=True)
            tbl.add_column("数量", style="bold", justify="right")
            total = 0
            for r in rows:
                tbl.add_row(r[0], r[1])
                total += int(r[1]) if r[1].isdigit() else 0
            parts.append(tbl)
            parts.append(f"[dim]总节点: {total}[/dim]\n")

    # 边统计表
    if ok2:
        rows = _parse_md_table(out2)
        if rows:
            tbl = Table(title="边统计", box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column("类型", style="magenta", no_wrap=True)
            tbl.add_column("数量", style="bold", justify="right")
            total_edges = 0
            for r in rows:
                tbl.add_row(r[0], r[1])
                total_edges += int(r[1]) if r[1].isdigit() else 0
            parts.append(tbl)
            parts.append(f"[dim]总边: {total_edges}[/dim]\n")

    # 社区数
    if ok3:
        rows = _parse_md_table(out3)
        if rows and rows[0]:
            parts.append(f"[bold]社区数: {rows[0][0]}[/bold] (Leiden 聚类)\n")

    # 高出度函数
    if ok4:
        rows = _parse_md_table(out4)
        if rows:
            tbl = Table(title="Top 调用者", box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column("函数", style="bold cyan", no_wrap=True)
            tbl.add_column("文件", style="dim")
            tbl.add_column("调用数", style="bold yellow", justify="right")
            for r in rows:
                if len(r) >= 3:
                    tbl.add_row(r[0], r[1], r[2])
            parts.append(tbl)

    # 输出 Panel
    from rich.console import Group
    panel = Panel(Group(*parts), title=f"[bold]{repo_name}[/bold] — 代码图谱", border_style="blue")
    console.print(panel)


def cmd_graph_query(args):
    """搜索图谱中的符号"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]尚未建立图索引，请先运行: cb graph index {repo_name}[/yellow]")
        return

    keywords = args.keywords
    ok, out = run_gitnexus(gn, "query", keywords, "--repo", repo_name)
    if not ok or not out:
        console.print("[red]查询失败或无结果[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        console.print(out)
        return

    # 解析 processes
    processes = data.get("processes", [])
    if processes:
        tbl = Table(title=f"执行流 ({len(processes)})", box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column("ID", style="dim", no_wrap=True)
        tbl.add_column("摘要", style="bold cyan")
        tbl.add_column("步数", justify="right")
        tbl.add_column("类型", style="magenta")
        for p in processes[:15]:
            tbl.add_row(
                p.get("id", ""),
                p.get("summary", ""),
                str(p.get("step_count", "")),
                p.get("process_type", ""),
            )
        console.print(tbl)

    # 解析 definitions
    defs = data.get("definitions", [])
    if defs:
        tbl = Table(title=f"符号定义 ({len(defs)})", box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column("名称", style="bold cyan", no_wrap=True)
        tbl.add_column("文件", style="dim")
        tbl.add_column("行号", style="yellow", justify="right")
        for d in defs[:20]:
            name = d.get("name", "")
            fpath = d.get("filePath", "")
            line = str(d.get("startLine", ""))
            tbl.add_row(name, fpath, line)
        console.print(tbl)

    # process_symbols
    syms = data.get("process_symbols", [])
    if syms:
        tbl = Table(title=f"流程符号 ({len(syms)})", box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column("名称", style="bold cyan", no_wrap=True)
        tbl.add_column("文件", style="dim")
        tbl.add_column("模块", style="magenta")
        tbl.add_column("流程", style="dim")
        for s in syms[:15]:
            tbl.add_row(
                s.get("name", ""),
                s.get("filePath", ""),
                s.get("module", ""),
                s.get("process_id", ""),
            )
        console.print(tbl)

    total = len(processes) + len(defs) + len(syms)
    if total == 0:
        console.print("[dim]无匹配结果[/dim]")
    else:
        console.print(f"\n[dim]共 {total} 条结果[/dim]")


def cmd_graph_deps(args):
    """显示跨模块依赖图"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]尚未建立图索引，请先运行: cb graph index {repo_name}[/yellow]")
        return

    # 跨文件函数调用统计
    ok, out = run_gitnexus(gn, "cypher",
        "MATCH (a:Function)-[r:CodeRelation {type: 'CALLS'}]->(b) "
        "WHERE a.filePath <> b.filePath "
        "RETURN a.filePath, b.filePath, count(*) AS weight "
        "ORDER BY weight DESC LIMIT 30",
        "--repo", repo_name)

    if not ok or not out:
        console.print("[red]查询失败[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    tbl = Table(title=f"{repo_name} — 跨模块依赖 (CALLS)", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column("调用方", style="bold cyan")
    tbl.add_column("→", style="dim", no_wrap=True)
    tbl.add_column("被调用方", style="bold green")
    tbl.add_column("调用数", style="yellow", justify="right")

    rows = _parse_md_table(out)
    for r in rows:
        if len(r) >= 3:
            tbl.add_row(r[0], "→", r[1], r[2])

    if not rows:
        console.print("[dim]无跨模块调用边[/dim]")
    else:
        console.print(tbl)
        console.print(f"\n[dim]{len(rows)} 条跨文件调用关系[/dim]")


def cmd_graph_community(args):
    """显示 Leiden 社区结构"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]尚未建立图索引，请先运行: cb graph index {repo_name}[/yellow]")
        return

    # 查询社区列表
    ok, out = run_gitnexus(gn, "cypher",
        "MATCH (c:Community) RETURN c.id, c.label, c.symbolCount, c.cohesion "
        "ORDER BY c.symbolCount DESC",
        "--repo", repo_name)

    if not ok or not out:
        console.print("[red]查询失败[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    communities = _parse_md_table(out)

    if not communities:
        console.print("[dim]无社区数据[/dim]")
        return

    # 查询 top 8 社区的成员 (并行)
    member_map = {}
    top_ids = [c[0] for c in communities[:8]]

    def _fetch_members(comm_id):
        ok, mout = run_gitnexus(gn, "cypher",
            f"MATCH (s)-[r:CodeRelation {{type: 'MEMBER_OF'}}]->(c:Community {{id: '{comm_id}'}}) "
            f"RETURN s.name AS name LIMIT 8",
            "--repo", repo_name, timeout=15)
        names = []
        if ok and mout:
            for r in _parse_md_table(mout):
                if r and r[0]:
                    names.append(r[0])
        return comm_id, names

    with ThreadPoolExecutor(max_workers=8) as pool:
        for comm_id, names in pool.map(lambda cid: _fetch_members(cid), top_ids):
            member_map[comm_id] = names

    # 渲染表格
    tbl = Table(title=f"{repo_name} — Leiden 社区", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column("ID", style="dim", no_wrap=True)
    tbl.add_column("域", style="magenta", no_wrap=True)
    tbl.add_column("符号数", style="bold yellow", justify="right")
    tbl.add_column("凝聚度", style="cyan", justify="right")
    tbl.add_column("成员 (采样)", style="dim")

    for c in communities:
        comm_id = c[0]
        members = member_map.get(comm_id, [])
        members_str = ", ".join(members[:6])
        if len(members) > 6:
            members_str += " ..."
        cohesion = c[3]
        try:
            cohesion = f"{float(cohesion):.2f}"
        except ValueError:
            pass
        tbl.add_row(comm_id, c[1], c[2], cohesion, members_str)

    console.print(tbl)
    console.print(f"\n[dim]共 {len(communities)} 个社区[/dim]")


def cmd_graph(args):
    """GitNexus 代码图谱分析 (调度器)"""
    graph_cmd = getattr(args, "graph_cmd", "overview") or "overview"
    dispatch = {
        "index": cmd_graph_index,
        "overview": cmd_graph_overview,
        "query": cmd_graph_query,
        "deps": cmd_graph_deps,
        "community": cmd_graph_community,
    }
    fn = dispatch.get(graph_cmd, cmd_graph_overview)
    fn(args)


# ---------------------------------------------------------------------------
# doc 命令 - 为仓库生成 Obsidian 项目文档
# ---------------------------------------------------------------------------

def _extract_section(text: str, heading: str) -> str:
    """从 markdown 文本中提取指定标题的内容段落（感知代码块）"""
    lines = text.split("\n")
    result = []
    capturing = False
    in_code_block = False
    level = 0
    for line in lines:
        if capturing:
            # 跟踪代码块状态
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
            # 代码块内不判断标题
            if not in_code_block and line.startswith("#"):
                cur = len(line) - len(line.lstrip("#"))
                if cur <= level:
                    break
            result.append(line)
        elif heading.lower() in line.lower() and line.lstrip().startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            capturing = True
    return "\n".join(result).strip()


def _find_key_diagrams(repo_path: Path, max_count: int = 12) -> list[Path]:
    """查找项目中的关键架构图（优先 docs/design/，排除自动生成的图）"""
    # 排除自动生成的目录
    skip_dirs = {"api", "html", "doxygen", "generated", "build", "node_modules"}

    def _is_skipped(p: Path) -> bool:
        return any(part.lower() in skip_dirs for part in p.relative_to(repo_path).parts)

    diagrams = []
    # 优先 docs/design/
    design_dir = repo_path / "docs" / "design"
    if design_dir.is_dir():
        diagrams.extend(sorted(design_dir.glob("*.png")))
    # 根目录图片
    for img in sorted(repo_path.glob("*.png")):
        if img not in diagrams:
            diagrams.append(img)
    # docs 下其他手动目录
    docs_dir = repo_path / "docs"
    if docs_dir.is_dir():
        for img in sorted(docs_dir.rglob("*.png")):
            if img not in diagrams and not _is_skipped(img):
                diagrams.append(img)
            if len(diagrams) >= max_count * 3:
                break
    return diagrams[:max_count]


def _read_file_safe(path: Path, max_lines: int = 500) -> str:
    """安全读取文件，限制行数"""
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return "\n".join(lines[:max_lines])
    except Exception:
        return ""


def cmd_doc(args):
    """为仓库生成 Obsidian 项目文档"""
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return
    repo_name = repo_path.name

    # 扫描仓库信息
    info = scan_repo(repo_path, full=True)
    if not info:
        console.print(f"[red]无法扫描: {repo_name}[/red]")
        return

    console.print(f"[bold]生成文档: {repo_name}[/bold]\n")

    # ── 收集详细信息 ──
    branches = run_git(repo_path, "branch", "--list").split("\n")
    branches = [b.strip().lstrip("* ") for b in branches if b.strip()]
    tags = run_git(repo_path, "tag", "--list").split("\n")
    tags = [t for t in tags if t.strip()]
    latest_tag = tags[-1] if tags else "无"

    contributors_out = run_git(repo_path, "shortlog", "-sn", "HEAD")
    contributors = []
    for line in contributors_out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            contributors.append((parts[1], int(parts[0].strip())))

    lang_detail = detect_language_detail(repo_path)
    total_files = sum(c for _, c in lang_detail) or 1
    lang_str = ", ".join(f"{lang} {count * 100 // total_files}%" for lang, count in lang_detail[:5])

    week_n = int(w) if (w := run_git(repo_path, "rev-list", "--count", "--since=7 days ago", "HEAD")).isdigit() else 0
    month_n = int(m) if (m := run_git(repo_path, "rev-list", "--count", "--since=30 days ago", "HEAD")).isdigit() else 0

    recent_log = run_git(repo_path, "log", "-15", "--format=%aI|%s")
    recent_commits = []
    for line in recent_log.split("\n"):
        if "|" not in line:
            continue
        parts = line.split("|", 1)
        try:
            dt = datetime.fromisoformat(parts[0])
            recent_commits.append((relative_time(dt), parts[1]))
        except ValueError:
            pass

    # ── 读取项目文档 ──
    readme = _read_file_safe(repo_path / "README.md")
    claude_md = _read_file_safe(repo_path / "CLAUDE.md")

    # 提取关键段落
    overview = ""
    if claude_md:
        overview = _extract_section(claude_md, "项目概述") or _extract_section(claude_md, "概述") or _extract_section(claude_md, "Overview")
    if not overview and readme:
        # 取 README 第一个非标题段落
        in_section = False
        buf = []
        for line in readme.split("\n"):
            if line.startswith("# "):
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section:
                buf.append(line)
        overview = "\n".join(buf).strip()

    architecture = ""
    if claude_md:
        architecture = _extract_section(claude_md, "架构设计") or _extract_section(claude_md, "架构") or _extract_section(claude_md, "Architecture")

    # ── 查找关键图表 ──
    diagrams = _find_key_diagrams(repo_path)

    # ── 创建 Obsidian 目录 ──
    vault_dir = OBSIDIAN_VAULT / "Projects" / repo_name
    assets_dir = vault_dir / "assets"
    vault_dir.mkdir(parents=True, exist_ok=True)
    # 清理旧 assets
    if assets_dir.is_dir():
        shutil.rmtree(assets_dir)

    # 复制图片
    copied_imgs = []
    if diagrams:
        assets_dir.mkdir(exist_ok=True)
        for src in diagrams:
            dst = assets_dir / src.name
            shutil.copy2(src, dst)
            copied_imgs.append(src.name)
            console.print(f"  [dim]复制: {src.relative_to(repo_path)}[/dim]")

    # ── 目录结构 ──
    tree_out = ""
    try:
        r = subprocess.run(
            ["find", str(repo_path / "src"), "-type", "d", "-maxdepth", "2"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            dirs = sorted(r.stdout.strip().split("\n"))
            tree_lines = []
            for d in dirs:
                rel = Path(d).relative_to(repo_path)
                depth = len(rel.parts) - 1
                name = rel.parts[-1] if rel.parts else ""
                tree_lines.append("  " * depth + name + "/")
            tree_out = "\n".join(tree_lines)
    except Exception:
        pass

    # ── docs 目录索引 ──
    docs_index = []
    docs_dir = repo_path / "docs"
    if docs_dir.is_dir():
        for sub in sorted(docs_dir.iterdir()):
            if sub.is_dir():
                count = sum(1 for _ in sub.rglob("*") if _.is_file())
                docs_index.append(f"- `docs/{sub.name}/` ({count} files)")

    # ── 生成 Markdown ──
    today = datetime.now().strftime("%Y-%m-%d")
    home = str(Path.home())
    path_display = str(repo_path).replace(home, "~")

    md_parts = []
    # frontmatter
    lang_tag = info.get("lang", "").lower() or "unknown"
    md_parts.append(f"""---
tags:
  - project
  - {lang_tag}
repo: "{path_display}"
remote: "{info.get('remote_url', '')}"
created: {today}
updated: {today}
---""")

    # 标题
    title_line = repo_name
    if readme:
        for line in readme.split("\n"):
            if line.startswith("# "):
                title_line = line[2:].strip()
                break
    md_parts.append(f"\n# {title_line}\n")

    # 基本信息表 (callout 样式)
    branch_extra = f" (+{len(branches) - 1} branches)" if len(branches) > 1 else ""
    contribs = ", ".join(f"{name}" for name, _ in contributors[:5])
    status_emoji = "✅" if info["dirty"] == 0 else "🔶"
    status_text = "干净" if info["dirty"] == 0 else f"{info['dirty']} 未提交变更"
    md_parts.append(f"""> [!info] 基本信息
> | 属性 | 值 |
> |------|------|
> | 路径 | `{path_display}` |
> | 远程 | `{info.get('remote_url', '无')}` |
> | 分支 | `{info['branch']}`{branch_extra} |
> | 语言 | {lang_str} |
> | 提交 | **{info['commits']}** commits (本周 {week_n} / 本月 {month_n}) |
> | 贡献者 | {len(contributors)} ({contribs}) |
> | 标签 | {len(tags)} tags (latest: {latest_tag}) |
> | 状态 | {status_emoji} {status_text} |
""")

    # 项目概述 (用 Obsidian callout)
    if overview:
        # 将概述包装为 callout
        callout_lines = overview.split("\n")
        callout = "> [!abstract] 项目概述\n" + "\n".join(f"> {l}" for l in callout_lines)
        md_parts.append(f"{callout}\n")

    # 架构 (限制长度，保留关键信息)
    if architecture:
        # 截断过长的架构段，保留前 60 行
        arch_lines = architecture.split("\n")
        if len(arch_lines) > 60:
            # 确保代码块闭合
            trimmed = arch_lines[:60]
            open_blocks = sum(1 for l in trimmed if l.strip().startswith("```"))
            if open_blocks % 2 != 0:
                trimmed.append("```")
            trimmed.append(f"\n> *完整架构详见 CLAUDE.md ({len(arch_lines)} 行)*")
            architecture = "\n".join(trimmed)
        md_parts.append(f"## 架构\n\n{architecture}\n")

    # 关键图表（使用 Obsidian wikilink 嵌入）
    if copied_imgs:
        md_parts.append("## 关键图表\n")
        for img in copied_imgs:
            label = img.replace(".png", "").replace("_", " ")
            md_parts.append(f"### {label}\n\n![[{img}]]\n")

    # 目录结构
    if tree_out:
        md_parts.append(f"## 源码结构\n\n```\n{tree_out}\n```\n")

    # 文档索引 (callout)
    if docs_index:
        lines = ["> [!folder]- 文档索引"] + [f"> {item}" for item in docs_index]
        md_parts.append("\n".join(lines) + "\n")

    # 最近活动 (callout, 可折叠)
    if recent_commits:
        lines = ["> [!timeline]- 最近活动"]
        for rel, msg in recent_commits:
            # 按类型着色提示
            prefix = "🟢" if msg.startswith("feat") else "🟡" if msg.startswith("fix") else "⚪"
            lines.append(f"> {prefix} **{rel}** — {msg}")
        md_parts.append("\n".join(lines) + "\n")

    # 写入
    doc_path = vault_dir / f"{repo_name}.md"
    doc_path.write_text("\n".join(md_parts), encoding="utf-8")

    console.print(f"\n[green]✓ 已生成: {doc_path}[/green]")
    console.print(f"  [dim]{len(copied_imgs)} 张图表 | {len(recent_commits)} 条提交记录[/dim]")


GLOBAL_FLAGS = {"--path", "--sort", "--filter", "--json", "--watch"}
# --sort/--path/--filter/--watch 后面跟一个值
GLOBAL_FLAGS_WITH_VALUE = {"--path", "--sort", "--filter", "--watch"}


def preprocess_argv(argv: list[str]) -> list[str]:
    """将全局选项移到子命令之前，允许 `cb health --filter foo` 的用法"""
    subcommands = {
        "dashboard", "activity", "health", "detail", "stats",
        "open", "dirty", "each", "pull", "push", "commit", "stash", "grep",
        "doc", "graph",
    }
    # 找到子命令位置
    sub_idx = None
    for i, arg in enumerate(argv):
        if arg in subcommands:
            sub_idx = i
            break
    if sub_idx is None:
        return argv

    before = argv[:sub_idx]
    subcmd = argv[sub_idx]
    after = argv[sub_idx + 1:]

    # 从 after 中提取全局选项，移到 before
    new_after = []
    i = 0
    while i < len(after):
        arg = after[i]
        if arg in GLOBAL_FLAGS:
            before.append(arg)
            if arg in GLOBAL_FLAGS_WITH_VALUE and i + 1 < len(after):
                before.append(after[i + 1])
                i += 2
            else:
                i += 1
        else:
            new_after.append(arg)
            i += 1

    return before + [subcmd] + new_after


def main():
    sys.argv[1:] = preprocess_argv(sys.argv[1:])

    parser = argparse.ArgumentParser(
        prog="codeboard",
        description="CodeBoard - 本地代码仓库仪表盘",
    )
    parser.add_argument("--path", default=str(DEFAULT_CODE_DIR), help="扫描目录 (默认 ~/Code)")
    parser.add_argument("--sort", choices=["name", "activity", "commits", "changes"], default="activity", help="排序方式")
    parser.add_argument("--filter", default="", help="按名称过滤")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--watch", type=int, metavar="N", default=0, help="每 N 秒自动刷新")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("dashboard", help="主仪表盘 (默认)")
    sub.add_parser("activity", help="跨仓库活动时间线").add_argument("--limit", type=int, default=30, help="显示条数")
    sub.add_parser("health", help="健康检查报告")

    detail_parser = sub.add_parser("detail", help="单个仓库详情")
    detail_parser.add_argument("repo", help="仓库名称")

    sub.add_parser("stats", help="汇总统计")

    # lazygit 联动
    open_parser = sub.add_parser("open", help="用 lazygit 打开仓库")
    open_parser.add_argument("repo", help="仓库名称")
    open_parser.add_argument("panel", nargs="?", choices=["status", "branch", "log", "stash"], help="lazygit 聚焦面板")

    sub.add_parser("dirty", help="列出脏仓库，选择后用 lazygit 打开")
    sub.add_parser("each", help="逐个 lazygit 处理所有脏仓库")

    # 操作命令
    sub.add_parser("pull", help="批量 git pull 所有有远程的仓库")
    sub.add_parser("push", help="推送所有有 ahead 提交的仓库")

    commit_parser = sub.add_parser("commit", help="快速 commit 指定仓库")
    commit_parser.add_argument("repo", help="仓库名称")
    commit_parser.add_argument("-m", "--message", required=True, help="提交信息")
    commit_parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    stash_parser = sub.add_parser("stash", help="快速 stash 指定仓库")
    stash_parser.add_argument("repo", help="仓库名称")
    stash_parser.add_argument("action", nargs="?", choices=["push", "pop", "list"], default="push", help="stash 操作 (默认 push)")
    stash_parser.add_argument("-m", "--message", help="stash 备注")

    grep_parser = sub.add_parser("grep", help="跨仓库代码搜索")
    grep_parser.add_argument("pattern", help="搜索模式 (正则)")

    doc_parser = sub.add_parser("doc", help="为仓库生成 Obsidian 项目文档")
    doc_parser.add_argument("repo", help="仓库名称")

    # GitNexus 图谱分析: cb graph <repo> [action] [keywords]
    graph_parser = sub.add_parser("graph", help="GitNexus 代码图谱分析")
    graph_parser.add_argument("repo", help="仓库名称")
    graph_parser.add_argument("graph_cmd", nargs="?", default="overview",
                              choices=["index", "query", "deps", "community", "overview"],
                              help="操作: index|query|deps|community (默认 overview)")
    graph_parser.add_argument("keywords", nargs="?", default="", help="query 的搜索关键词")

    args = parser.parse_args()

    cmd = args.command or "dashboard"

    commands = {
        "dashboard": cmd_dashboard,
        "activity": cmd_activity,
        "health": cmd_health,
        "detail": cmd_detail,
        "stats": cmd_stats,
        "open": cmd_open,
        "dirty": cmd_dirty,
        "each": cmd_each,
        "pull": cmd_pull,
        "push": cmd_push,
        "commit": cmd_commit,
        "stash": cmd_stash,
        "grep": cmd_grep,
        "doc": cmd_doc,
        "graph": cmd_graph,
    }

    handler = commands.get(cmd)
    if not handler:
        return

    if args.watch > 0:
        signal.signal(signal.SIGINT, lambda *_: (console.print("\n[dim]Bye[/dim]"), sys.exit(0)))
        while True:
            console.clear()
            t0 = time.monotonic()
            handler(args)
            elapsed = time.monotonic() - t0
            console.print(f"\n[dim]每 {args.watch}s 刷新 | 耗时 {elapsed:.1f}s | Ctrl+C 退出[/dim]")
            time.sleep(args.watch)
    else:
        handler(args)


if __name__ == "__main__":
    main()
