# CodeBoard

[![CI](https://github.com/shaoyiyang/codeboard/actions/workflows/ci.yml/badge.svg)](https://github.com/shaoyiyang/codeboard/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Git repository dashboard for your local codebase. Scans all git repos under a directory and shows status, activity, health — with batch operations and lazygit integration.

```
╭────────────── CodeBoard ── ~/Code ── 48 repos ──────────────────────────────╮
│ Name               │ Branch   │ Last Commit │ Status │ Language │ Remote    │
│ codemaster         │ main     │ 7m ago      │   ●1   │ Python   │ github ↑3 │
│ managerAgent       │ main     │ 1h ago      │   ●4   │ Python   │ github ↑2 │
│ quant              │ main     │ 4d ago      │  ●15   │ Python   │ github    │
│ SEIR               │ main     │ 6d ago      │  ●26   │ Python   │ github    │
│ scip               │ master   │ 8d ago      │   ●4   │ C/C++    │ github    │
│ petsc              │ main     │ 1mo ago     │    ✓   │ C        │ github    │
│ ...                │          │             │        │          │           │
╰───────────────────────────── ● = uncommitted  ✓ = clean ────────────────────╯
```

## Features

- **Dashboard** — Overview of all repos: branch, last commit, dirty status, language, remote
- **Activity** — Cross-repo commit timeline
- **Health** — Find uncommitted changes, unpushed commits, repos behind remote, inactive repos
- **Detail** — Deep dive into a single repo: contributors, languages, recent commits
- **Stats** — Aggregate statistics: language distribution, weekly top, remote distribution
- **Grep** — Search code across all repos
- **Batch ops** — Pull all, push all, quick commit, stash
- **lazygit** — Open repos in lazygit, process dirty repos interactively
- **Doc** — Generate Obsidian project documentation (optional)
- **Graph** — Code graph analysis via GitNexus (optional)

## Install

```bash
pip install .
```

Or run directly:

```bash
python codeboard.py
```

## Quick Start

```bash
# Main dashboard
codeboard

# Or use the short alias after pip install
cb

# Filter repos by name
cb --filter simona

# Sort by dirty file count
cb --sort changes

# Cross-repo commit timeline
cb activity --limit 50

# Health check
cb health

# Single repo details
cb detail myrepo

# Summary statistics
cb stats

# Search code across all repos
cb grep "TODO"

# Batch pull all repos
cb pull

# Push all repos with ahead commits
cb push

# Quick commit
cb commit myrepo -m "feat: something" -y

# Stash / unstash
cb stash myrepo
cb stash myrepo pop

# Open in lazygit
cb open myrepo log

# Process all dirty repos one by one
cb each

# JSON output for piping
cb --json | jq '.[]'

# Auto-refresh every 10 seconds
cb --watch 10
```

## Configuration

Config file: `~/.config/codeboard/config.toml`

Generate a default config:

```bash
cb config
```

```toml
# Directory to scan for git repositories
scan_dir = "~/Code"

# Additional individual repos to include (outside scan_dir)
extra_repos = ["~/Projects/special-repo"]

# UI language: "auto", "en", or "zh"
lang = "auto"

# Path to Obsidian vault (for 'doc' command, optional)
# obsidian_vault = "~/Documents/Obsidian Vault"

# Path to gitnexus binary (for 'graph' command, optional)
# gitnexus_bin = ""
```

## Global Options

| Flag | Description |
|------|-------------|
| `--path <dir>` | Scan directory (default: `~/Code` or config) |
| `--sort name\|activity\|commits\|changes` | Sort order |
| `--filter <keyword>` | Filter repos by name |
| `--json` | JSON output for piping |
| `--watch N` | Auto-refresh every N seconds |
| `--lang en\|zh\|auto` | UI language |
| `--no-color` | Disable colored output |
| `-V, --version` | Show version |

Global options can be placed before or after the subcommand:

```bash
cb health --filter simona    # works
cb --filter simona health    # also works
```

## Commands

### View

| Command | Description |
|---------|-------------|
| `cb` / `cb dashboard` | Main dashboard with repo overview |
| `cb activity [--limit N]` | Cross-repo commit timeline (default 30) |
| `cb health` | Health check: uncommitted / unpushed / behind / no remote / inactive |
| `cb detail <repo>` | Single repo detail: languages, contributors, tags, recent commits |
| `cb stats` | Aggregate statistics |
| `cb grep <pattern>` | Search code across all repos (regex) |

### Operations

| Command | Description |
|---------|-------------|
| `cb pull` | Batch `git pull --ff-only` all repos with remote |
| `cb push` | Push all repos with ahead commits (requires confirmation) |
| `cb commit <repo> -m "msg"` | Quick `git add -A && commit` (use `-y` to skip confirmation) |
| `cb stash <repo> [push\|pop\|list]` | Quick stash operations |

### lazygit Integration

| Command | Description |
|---------|-------------|
| `cb open <repo> [panel]` | Open repo in lazygit (panel: status/branch/log/stash) |
| `cb dirty` | List dirty repos, select one to open in lazygit |
| `cb each` | Process all dirty repos one by one in lazygit |

### Optional

| Command | Description | Requires |
|---------|-------------|----------|
| `cb doc <repo>` | Generate Obsidian project documentation | Obsidian vault path in config |
| `cb graph <repo> [action]` | Code graph analysis | [gitnexus](https://github.com/nicolo-ribaudo/gitnexus) |
| `cb config` | Show or generate config file | — |
| `cb completions [bash\|zsh\|fish]` | Generate shell completion script | — |

## Shell Completion

```bash
# Bash (add to ~/.bashrc)
eval "$(cb completions bash)"

# Zsh (add to ~/.zshrc)
eval "$(cb completions zsh)"

# Fish (add to ~/.config/fish/completions/)
cb completions fish > ~/.config/fish/completions/cb.fish
```

## Requirements

- Python ≥ 3.11
- [rich](https://github.com/Textualize/rich) (terminal formatting)
- git
- [lazygit](https://github.com/jesseduffield/lazygit) (optional, for `open`/`dirty`/`each`)
- [gitnexus](https://github.com/nicolo-ribaudo/gitnexus) (optional, for `graph`)

**Windows note:** CodeBoard uses `sh -c` for batched git commands. On Windows, this requires [Git for Windows](https://gitforwindows.org/) which includes `sh`. WSL also works.

## Performance

- Scans 48 repos in ~1 second
- Single shell call per repo (6-9 git commands batched into one `sh -c`)
- 8-way parallel scanning via `ThreadPoolExecutor`
- Lazy language detection (skipped for commands that don't need it)

## Development

```bash
git clone https://github.com/shaoyiyang/codeboard.git
cd codeboard
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE)
