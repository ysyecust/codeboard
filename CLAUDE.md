# CodeBoard

本地代码仓库仪表盘 CLI 工具。扫描 `~/Code` 下所有 git 仓库，展示开发状态、活跃度、健康状况，并提供批量操作与 lazygit 联动能力。

## 项目结构

```
codemaster/
  codeboard.py    # 单文件，全部逻辑 (~1100行)
  CLAUDE.md       # 本文件
```

- **语言**: Python 3.14+
- **依赖**: `rich` (终端美化)，标准库 (`subprocess`, `concurrent.futures`, `argparse`, ...)
- **外部工具**: `git` (必须), `lazygit` (open/dirty/each 子命令需要)

## 使用方式

已配置 alias: `cb` = `python3 ~/Code/codemaster/codeboard.py`

### 子命令一览

```bash
# ── 查看 ──
cb                        # 主仪表盘 (默认)，按活跃度排序
cb activity [--limit N]   # 跨仓库提交时间线，默认 30 条
cb health                 # 健康检查：未提交/未推送/落后远程/无远程/不活跃
cb detail <repo>          # 单仓库详情：语言占比/贡献者/标签/活跃度曲线
cb stats                  # 汇总统计：语言分布/本周Top/远程分布
cb grep <pattern>         # 跨所有仓库搜索代码内容

# ── 操作 ──
cb pull                   # 批量 git pull 所有有远程的仓库 (--ff-only)
cb push                   # 推送所有有 ahead 提交的仓库 (需确认)
cb commit <repo> -m "msg" # 快速 add+commit 指定仓库 (需确认，-y 跳过)
cb stash <repo> [push|pop|list] [-m "msg"]  # 快速 stash 操作

# ── lazygit 联动 ──
cb open <repo> [panel]    # lazygit 打开仓库，panel 可选 status/branch/log/stash
cb dirty                  # 列出脏仓库，交互选择后 lazygit 打开
cb each                   # 逐个 lazygit 处理所有脏仓库
```

### 通用选项

```bash
--path <dir>              # 扫描目录，默认 ~/Code
--sort name|activity|commits|changes
--filter <keyword>        # 按仓库名模糊过滤
--json                    # JSON 输出，方便管道
--watch N                 # 每 N 秒自动刷新，Ctrl+C 退出
```

### 常用组合

```bash
cb --filter simona          # 只看 simona 系列
cb --sort changes           # 按脏文件数排序
cb activity --limit 50      # 最近 50 条提交
cb --watch 10               # 10 秒刷新的实时监控
cb --json | jq '.[]'        # 管道处理
cb open quant log           # lazygit 直接看 quant 的提交历史
cb each --filter simona     # 逐个处理 simona 相关脏仓库
cb grep "TODO" --filter simona  # 在 simona 系列中搜索 TODO
cb pull                     # 一键拉取所有仓库
cb push                     # 推送所有有 ahead 的仓库
cb commit quant -m "feat: xxx" -y  # 快速提交
cb stash quant              # 暂存 quant 的变更
cb stash quant pop          # 恢复暂存
```

## 架构设计

### 核心流程

```
main() → argparse 解析 → handler(args)
                              ↓
                    scan_all() 并行扫描
                    ├── ThreadPoolExecutor(max_workers=8)
                    └── scan_repo() × N (每仓库 1 次 shell 调用)
                              ↓
                    sort_repos() → rich 渲染输出
```

### 命令分类

```
查看类 (只读)     操作类 (写入)      lazygit 联动
─────────────     ──────────────     ─────────────
dashboard         pull               open
activity          push               dirty
health            commit             each
detail            stash
stats
grep
```

### 性能关键决策

1. **单次 shell 调用**: `scan_repo()` 用 `SCAN_SCRIPT_BASE/FULL` 把 6-9 条 git 命令合并为 1 个 `sh -c` 调用，通过 `%%TAG%%` 标记解析输出
2. **8 路并行**: `ThreadPoolExecutor(max_workers=8)` 并行扫描所有仓库
3. **延迟语言检测**: `full=False` 时跳过 `git ls-files`，health/dirty 等不需要语言信息的命令更快
4. **43 仓库全量扫描 ~1 秒**

### 安全设计

- `pull` 使用 `--ff-only`，不会产生 merge commit
- `push` 和 `commit` 默认需要用户确认（commit 可用 `-y` 跳过）
- `stash` 默认 `--include-untracked`，不会丢失文件
- 所有写操作都有明确的执行反馈（✓ 成功 / ✗ 失败 + 原因）

### 关键函数

| 函数 | 作用 |
|------|------|
| `scan_repo(path, full)` | 单仓库信息提取，核心函数 |
| `scan_all(dir, full, filter)` | 并行扫描入口 |
| `SCAN_SCRIPT_BASE/FULL` | shell 脚本模板，合并 git 调用 |
| `find_repo(dir, name)` | 仓库名模糊匹配 |
| `relative_time(dt)` | datetime → 中文相对时间 |
| `detect_remote_type(url)` | remote URL → github/gitlab/gitee/... |
| `LANG_MAP` / `IGNORE_EXTS` | 文件扩展名 → 语言映射 & 忽略列表 |

### scan_repo 返回的 dict 结构

```python
{
    "name": "quant",              # 文件夹名
    "path": "/Users/.../quant",   # 绝对路径
    "branch": "main",             # 当前分支
    "last_time": datetime,        # 最后提交时间 (datetime 对象)
    "last_time_rel": "2天前",     # 相对时间 (中文)
    "last_time_ts": 1771742393.0, # Unix 时间戳 (排序用)
    "last_msg": "feat: ...",      # 最后提交信息
    "dirty": 36,                  # 未提交变更文件数
    "commits": 33,                # 总提交数
    "remote_url": "git@...",      # remote origin URL
    "remote_type": "github",      # github/gitlab/gitee/other/none
    "ahead": 0,                   # 领先远程提交数
    "behind": 0,                  # 落后远程提交数
    "lang": "Python",             # 主要语言 (full=True 时才有)
}
```

## 开发约定

- **单文件原则**: 所有逻辑保持在 `codeboard.py` 一个文件中
- **无状态**: 不使用缓存、数据库、配置文件，每次运行实时扫描
- **输出用 rich**: 表格用 `Table`，面板用 `Panel`，着色用 `Text`
- **新子命令模式**: 写 `cmd_xxx(args)` 函数 → 注册到 `main()` 的 `commands` dict 和 `argparse` 子解析器
- **写操作需确认**: push/commit 等写操作默认询问用户确认
- **lazygit 联动**: 用 `os.execvp` 替换当前进程 (open)，用 `subprocess.run` 串行调用 (each)
- **错误处理**: git 命令超时/失败静默返回空字符串，不中断整体扫描

## 扩展指南

### 添加新子命令

```python
# 1. 写命令函数
def cmd_xxx(args):
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=True, filter_kw=args.filter)
    # ... 逻辑 ...

# 2. 在 main() 中注册
xxx_parser = sub.add_parser("xxx", help="描述")
xxx_parser.add_argument(...)  # 如有额外参数

commands = {
    ...,
    "xxx": cmd_xxx,
}
```

### 添加新语言检测

在 `LANG_MAP` 字典中加扩展名映射即可:
```python
".hs": "Haskell",
```

### 添加新远程类型

在 `detect_remote_type()` 中加判断:
```python
if "coding.net" in url_lower:
    return "coding"
```
