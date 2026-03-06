# CodeBoard

Git repository dashboard CLI. Scans all git repos under a directory, shows status/activity/health, with batch operations and lazygit integration.

## Project Structure

```
codemaster/
  codeboard.py    # Single file, all logic (~3070 lines)
  pyproject.toml  # Packaging (setuptools, console_scripts: cb/codeboard)
  README.md       # English documentation
  LICENSE         # MIT
  CLAUDE.md       # This file
```

- **Language**: Python 3.11+
- **Dependencies**: `rich` (terminal formatting), stdlib (`subprocess`, `concurrent.futures`, `argparse`, `tomllib`, ...)
- **External tools**: `git` (required), `lazygit` (optional, for open/dirty/each), `gitnexus` (optional, for graph)

## Install & Usage

```bash
pip install .          # installs `cb` and `codeboard` commands
# or run directly:
python codeboard.py
```

### Commands

```bash
# ── View ──
cb                        # Main dashboard (default), sorted by activity
cb activity [--limit N]   # Cross-repo commit timeline (default 30)
cb health                 # Health check: uncommitted/unpushed/behind/no-remote/inactive
cb detail <repo>          # Single repo detail: languages/contributors/tags/activity
cb stats                  # Aggregate statistics: language dist/weekly top/remote dist
cb grep <pattern>         # Search code across all repos

# ── Operations ──
cb pull                   # Batch git pull --ff-only all repos with remote
cb push                   # Push all repos with ahead commits (requires confirm)
cb commit <repo> -m "msg" # Quick add+commit (requires confirm, -y to skip)
cb stash <repo> [push|pop|list] [-m "msg"]  # Quick stash ops

# ── lazygit ──
cb open <repo> [panel]    # Open in lazygit (panel: status/branch/log/stash)
cb dirty                  # List dirty repos, select one for lazygit
cb each                   # Process all dirty repos one by one in lazygit

# ── GitNexus Code Graph ──
cb graph <repo>                    # Graph overview: nodes/edges/communities/top callers
cb graph <repo> index              # Index repo into knowledge graph (required first)
cb graph <repo> query <keywords>   # Search symbols: processes + definitions + symbols
cb graph <repo> deps               # Cross-module dependency graph (CALLS edges)
cb graph <repo> community          # Leiden community structure (with member sampling)
cb graph <repo> report             # Generate Obsidian code graph doc (Mermaid charts)
cb graph <repo> hierarchy          # Class inheritance tree (Rich Tree)
cb graph <repo> hubs               # High-reference symbols (Hub Nodes)
cb graph <repo> modules            # Module file distribution (bar chart)

# ── Other ──
cb doc <repo>             # Generate Obsidian project documentation
cb config                 # Show or generate config file
```

### Global Options

```bash
--path <dir>              # Scan directory (default: ~/Code or config)
--sort name|activity|commits|changes
--filter <keyword>        # Filter repos by name
--json                    # JSON output for piping
--watch N                 # Auto-refresh every N seconds
--lang en|zh|auto         # UI language (default: auto-detect)
--no-color                # Disable colored output
-V, --version             # Show version
```

## Architecture

### Core Flow

```
main() → argparse → preprocess_argv() → handler(args)
                                            ↓
                                  scan_all() parallel scan
                                  ├── ThreadPoolExecutor(max_workers=8)
                                  └── scan_repo() × N (1 shell call per repo)
                                            ↓
                                  sort_repos() → rich rendering
```

### i18n System

```python
_I18N = {"en": {...}, "zh": {...}}   # 166 keys, flat dict
_ui_lang = "auto"                     # from config or --lang flag
T(key, **kw) → str                   # lookup + format
```

- Auto-detects from `locale.getdefaultlocale()`
- Override with `--lang en|zh` or config `lang = "en"`
- Covers all CLI output + generated Markdown (doc/graph report)

### Configuration

```
~/.config/codeboard/config.toml
├── scan_dir = "~/Code"
├── extra_repos = []
├── lang = "auto"
├── obsidian_vault = ""
└── gitnexus_bin = ""
```

Loaded via `_load_config()` → `CFG` dict at import time. `cb config` generates default.

### Command Categories

```
View (read-only)  Operations (write)  lazygit       Graph Analysis
──────────────    ────────────────    ──────────    ──────────────
dashboard         pull                open          graph overview
activity          push                dirty         graph index
health            commit              each          graph query
detail            stash                             graph deps
stats                                               graph community
grep                                                graph report
                                                    graph hierarchy
                                                    graph hubs
                                                    graph modules
```

### Performance

1. **Single shell call**: `scan_repo()` batches 6-9 git commands into 1 `sh -c` call, parsed via `%%TAG%%` markers
2. **8-way parallel**: `ThreadPoolExecutor(max_workers=8)`
3. **Lazy language detection**: `full=False` skips `git ls-files`
4. **~1s for 48 repos**

### Key Functions

| Function | Purpose |
|----------|---------|
| `scan_repo(path, full)` | Single repo info extraction, core function |
| `scan_all(dir, full, filter)` | Parallel scan entry point |
| `SCAN_SCRIPT_BASE/FULL` | Shell script templates, batched git calls |
| `find_repo(dir, name)` | Fuzzy repo name matching |
| `T(key, **kw)` | i18n string lookup |
| `_load_config()` | TOML config loader |
| `relative_time(dt)` | datetime → localized relative time |
| `detect_remote_type(url)` | remote URL → github/gitlab/gitee/... |
| `require_gitnexus()` | Check gitnexus availability |
| `run_gitnexus(gn, subcmd, ...)` | gitnexus subprocess wrapper (output on stderr) |
| `_parse_md_table(raw)` | Parse gitnexus cypher markdown table output |
| `_graph_require(args)` | Graph commands common prerequisite check |
| `_bar_chart_text(items)` | Text bar chart generation (for report) |

### scan_repo Return Dict

```python
{
    "name": "quant",              # directory name
    "path": "/Users/.../quant",   # absolute path
    "branch": "main",             # current branch
    "last_time": datetime,        # last commit time
    "last_time_rel": "2d ago",    # relative time (localized)
    "last_time_ts": 1771742393.0, # unix timestamp (for sorting)
    "last_msg": "feat: ...",      # last commit message
    "dirty": 36,                  # uncommitted file count
    "commits": 33,                # total commits
    "remote_url": "git@...",      # remote origin URL
    "remote_type": "github",      # github/gitlab/gitee/other/none
    "ahead": 0,                   # commits ahead of remote
    "behind": 0,                  # commits behind remote
    "lang": "Python",             # primary language (full=True only)
}
```

## Development Conventions

- **Single file**: All logic stays in `codeboard.py`
- **Config**: TOML at `~/.config/codeboard/config.toml`, loaded once at import
- **i18n**: All user-facing strings use `T(key)`, add keys to both `en` and `zh` in `_I18N`
- **Output via rich**: Tables → `Table`, panels → `Panel`, coloring → `Text`
- **New subcommand pattern**: Write `cmd_xxx(args)` → register in `main()` commands dict + argparse subparser
- **Write ops need confirmation**: push/commit default to asking user
- **lazygit integration**: `os.execvp` for open, `subprocess.run` for each
- **Error handling**: git timeout/failure returns empty string silently, doesn't break scan

## Extension Guide

### Adding a New Subcommand

```python
# 1. Write command function
def cmd_xxx(args):
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=True, filter_kw=args.filter)
    # ... logic ...

# 2. Register in main()
xxx_parser = sub.add_parser("xxx", help="description")
xxx_parser.add_argument(...)

commands = {
    ...,
    "xxx": cmd_xxx,
}
```

### Adding i18n Strings

```python
# In _I18N dict, add to BOTH "en" and "zh":
"en": { ..., "my_key": "English text {n}", },
"zh": { ..., "my_key": "中文文本 {n}", },

# Use in code:
console.print(T("my_key", n=42))
```

### Adding Language Detection

In `LANG_MAP`:
```python
".hs": "Haskell",
```

### Adding Remote Type Detection

In `detect_remote_type()`:
```python
if "coding.net" in url_lower:
    return "coding"
```
