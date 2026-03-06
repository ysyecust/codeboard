#!/usr/bin/env python3
"""CodeBoard — Git repository dashboard for your local codebase."""

__version__ = "0.1.0"

import argparse
import json
import locale
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ── Configuration ──────────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config" / "codeboard"
CONFIG_FILE = CONFIG_DIR / "config.toml"

_DEFAULT_CONFIG = {
    "scan_dir": str(Path.home() / "Code"),
    "extra_repos": [],
    "lang": "auto",
    "obsidian_vault": "",
    "gitnexus_bin": "",
}


def _load_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    if CONFIG_FILE.is_file():
        with open(CONFIG_FILE, "rb") as f:
            cfg.update(tomllib.load(f))
    return cfg


def _generate_default_config() -> str:
    return """\
# CodeBoard configuration
# See: https://github.com/shaoyiyang/codeboard

# Directory to scan for git repositories
scan_dir = "~/Code"

# Additional individual repos to include (outside scan_dir)
extra_repos = []

# UI language: "auto", "en", or "zh"
lang = "auto"

# Path to Obsidian vault (for 'doc' command, optional)
# obsidian_vault = "~/Documents/Obsidian Vault"

# Path to gitnexus binary (for 'graph' command, optional)
# gitnexus_bin = ""
"""


CFG = _load_config()

# Derive globals from config
DEFAULT_CODE_DIR = Path(CFG["scan_dir"]).expanduser()
EXTRA_REPOS = [Path(p).expanduser() for p in CFG["extra_repos"]]
OBSIDIAN_VAULT = Path(CFG["obsidian_vault"]).expanduser() if CFG["obsidian_vault"] else Path.home() / "Documents" / "Obsidian Vault"
GITNEXUS_BIN = CFG["gitnexus_bin"] or ""

# ── i18n ───────────────────────────────────────────────────────────────────────

_I18N: dict[str, dict[str, str]] = {
    "en": {
        # relative time
        "just_now": "just now", "secs_ago": "{n}s ago", "mins_ago": "{n}m ago",
        "hours_ago": "{n}h ago", "days_ago": "{n}d ago", "months_ago": "{n}mo ago",
        "years_ago": "{n}y ago", "no_commits": "no commits",
        # dashboard
        "col_name": "Name", "col_branch": "Branch", "col_last_commit": "Last Commit",
        "col_status": "Status", "col_language": "Language", "col_commits": "Commits",
        "col_remote": "Remote", "dashboard_sub": "● = uncommitted  ✓ = clean",
        # activity
        "col_time": "Time", "col_repo": "Repo", "col_author": "Author", "col_message": "Message",
        # health
        "health_dirty": "  ⚠ Uncommitted changes", "health_ahead": "  ⚠ Unpushed commits",
        "health_behind": "  ⚠ Behind remote", "health_no_remote": "  ○ No remote",
        "health_inactive": "  ○ Inactive >30d", "health_ok": "  ✓ All clean",
        # detail
        "lbl_path": "Path", "lbl_remote": "Remote", "lbl_branch": "Branch", "lbl_tags": "Tags",
        "lbl_commits": "Commits", "lbl_contribs": "Contributors", "lbl_lang": "Language",
        "lbl_status": "Status", "lbl_recent": "Recent commits", "lbl_activity": "Activity",
        "none": "none", "this_week": "this week", "this_month": "this month",
        # stats
        "total_repos": "Total repos", "active_30d": "Active(30d)", "has_remote": "Has remote",
        "total_commits": "Total commits", "lang_dist": "Language distribution",
        "week_top": "Weekly top", "remote_dist": "Remote distribution",
        # dirty / each
        "all_clean": "All repos are clean", "col_changes": "Changes",
        "dirty_title": "Repos with uncommitted changes ({n})",
        "dirty_prompt": "Enter number to open with lazygit, Enter to exit",
        "invalid_num": "Invalid number",
        "processing_n": "Processing {n} dirty repos one by one",
        "each_hint": "Close lazygit → next repo, Ctrl+C to exit",
        "interrupted": "Interrupted", "all_done": "All done",
        # pull / push
        "no_remote_repos": "No repos with remote configured",
        "pull_prep": "Pulling {n} repos with remote",
        "updated_n": "  ✓ Updated ({n})", "failed_n": "  ✗ Failed ({n})",
        "up_to_date_n": "  ─ Up to date ({n})",
        "no_push_needed": "No repos need pushing",
        "confirm_push": "Confirm push {n} repos above? [y/N]",
        "cancelled": "Cancelled", "push_done": "Push complete",
        # commit / stash
        "missing_msg": "Missing commit message, use -m",
        "tree_clean": "{name}: working tree clean",
        "n_changes": "{name} — {n} changed files:",
        "n_more": "  ... {n} more files",
        "commit_msg_lbl": "Commit message", "confirm_commit": "Confirm git add -A && commit? [y/N]",
        "committed": "✓ Committed", "commit_fail": "✗ Commit failed:",
        "no_stash_needed": "{name}: working tree clean, nothing to stash",
        "stash_ok": "✓ {name}: stashed {n} changes", "stash_fail": "✗ Stash failed:",
        "stash_pop_ok": "✓ {name}: stash pop succeeded", "stash_pop_fail": "✗ Stash pop failed:",
        # grep
        "no_match": "No matches: {pattern}",
        # find_repo / require
        "multi_match": "Multiple matches: {hints}",
        "match_hint": "Hint: use full path to distinguish",
        "repo_not_found": "Repo not found: {name}",
        "lazygit_missing": "lazygit not installed", "gitnexus_missing": "gitnexus not found",
        "expected_path": "Expected path: {path}",
        # doc
        "gen_doc": "Generating doc: {name}", "cannot_scan": "Cannot scan: {name}",
        "doc_ok": "✓ Generated: {path}", "doc_stats": "{imgs} diagrams | {commits} commit records",
        "copying": "Copy: {path}",
        "doc_none": "none",
        "doc_clean": "clean", "doc_dirty": "{n} uncommitted changes",
        "doc_info": "Basic Info", "doc_attr": "Attribute", "doc_value": "Value",
        "doc_path": "Path", "doc_remote": "Remote", "doc_branch": "Branch",
        "doc_language": "Language", "doc_commits_week_month": "**{commits}** commits (this week {week} / this month {month})",
        "doc_contribs": "Contributors", "doc_tags": "Tags",
        "doc_status": "Status",
        "doc_overview": "Overview",
        "doc_arch": "Architecture",
        "doc_arch_full": "Full architecture in CLAUDE.md ({n} lines)",
        "doc_diagrams": "Key Diagrams", "doc_source_tree": "Source Structure",
        "doc_docs_index": "Documentation Index", "doc_recent": "Recent Activity",
        # graph report markdown templates
        "rpt_title": "Code Graph",
        "rpt_info": "Data Source",
        "rpt_gen_by": "Auto-generated by [GitNexus](https://github.com/nicobailon/gitnexus) knowledge graph engine.",
        "rpt_regen": "Regenerate: `cb graph {name} report`",
        "rpt_metric": "Metric", "rpt_value": "Value",
        "rpt_nodes": "Nodes", "rpt_edges": "Edges",
        "rpt_communities_label": "Communities",
        "rpt_processes_label": "Processes", "rpt_files_label": "Files",
        "rpt_idx_time": "Index Time",
        "rpt_related": "Related: [[{name}]]",
        "rpt_overview": "Graph Overview",
        "rpt_overview_desc": "The knowledge graph contains **{nodes:,}** nodes and **{edges:,}** edges, covering {files} source files.",
        "rpt_node_top3": "Nodes are primarily composed of {top3}.",
        "rpt_node_dist": "Node Type Distribution",
        "rpt_edge_dist": "Edge Type Distribution",
        "rpt_module_dist": "Module File Distribution",
        "rpt_pie_title": "Files by Module",
        "rpt_module": "Module", "rpt_file_count": "Files", "rpt_pct": "Pct",
        "rpt_cross_deps": "Cross-module Dependencies (Hot Calls)",
        "rpt_cross_desc": "File-level CALLS edges ranked by frequency, reflecting inter-module coupling:",
        "rpt_caller_file": "Caller File", "rpt_callee_file": "Callee File", "rpt_call_count": "Calls",
        "rpt_imports": "Module Import Relations",
        "rpt_hubs": "Hub Nodes (High References)",
        "rpt_hubs_desc": "Functions and classes referenced most by other symbols — the **core API** of the codebase:",
        "rpt_symbol": "Symbol", "rpt_file": "File", "rpt_refs": "References", "rpt_type": "Type",
        "rpt_top_callers": "Top Callers",
        "rpt_top_callers_desc": "Symbols that call the most other functions, typically **entry points or core dispatchers**:",
        "rpt_function": "Function", "rpt_call_n": "Calls",
        "rpt_proc_flows": "Process Flows",
        "rpt_proc_desc": "GitNexus detected **{n}** process flows via call chain tracing. Top {m}:",
        "rpt_file_index": "Key File Index",
        "rpt_file_index_desc": "AI navigation guide: files ranked by number of defined symbols, for quick understanding of each file's role.",
        "rpt_file_col": "File", "rpt_sym_count": "Symbols", "rpt_main_defs": "Main Definitions",
        "rpt_inherit": "Class Inheritance",
        "rpt_inherit_desc": "{n} inheritance relations, {m} base classes:",
        "rpt_parent": "Base Class", "rpt_child": "Subclasses",
        "rpt_structs": "Core Data Structures (Struct)",
        "rpt_structs_desc": "Indexed {n} Structs, by module:",
        "rpt_enums": "Enum Types",
        "rpt_namespaces": "Namespace Structure",
        "rpt_community_struct": "Community Structure (Leiden Clustering)",
        "rpt_community_desc": "Leiden algorithm detected **{n}** communities. Top communities by symbol count:",
        "rpt_involved_files": "Involved Files",
        "rpt_core_symbols": "Core Symbols",
        "rpt_comm_overview": "Community Overview",
        "rpt_comm_col": "Community", "rpt_domain": "Domain",
        "rpt_sym_n": "Symbols", "rpt_cohesion": "Cohesion",
        "rpt_edge_stats": "Edge Relation Statistics",
        "rpt_edge_type": "Edge Type", "rpt_meaning": "Meaning", "rpt_count": "Count",
        "rpt_edge_calls": "Function call", "rpt_edge_defines": "File defines symbol",
        "rpt_edge_imports": "File/module import", "rpt_edge_contains": "Directory contains file",
        "rpt_edge_member": "Namespace member", "rpt_edge_step": "Process step",
        "rpt_edge_extends": "Class inheritance",
        "rpt_code_graph_doc": "Code Graph",
        "rpt_xref_label": "GitNexus Code Graph",
        # graph
        "graph_ok": "✓ Generated: {path}",
        "graph_stats": "{nodes:,} nodes | {edges:,} edges | {communities} communities | {processes} processes",
        "xref_added": "  Added cross-reference to {name}.md",
        "graph_specify_repo": "Please specify a repo name",
        "graph_already_indexed": "⟳ {name} already indexed, will rebuild",
        "graph_cpp_warn": "⚠ C/C++ projects may take longer or be unstable to index",
        "graph_indexing": "Indexing: {name}",
        "graph_index_ok": "✓ Indexing complete: {name}",
        "graph_index_fail": "✗ Indexing failed (exit {code})",
        "graph_index_timeout": "✗ Indexing timed out (>180s)",
        "graph_not_indexed": "Not yet indexed, run first: cb graph {name} index",
        "graph_idx_time": "Index time: {time}",
        "graph_unknown": "unknown",
        "graph_node_stats": "Node Statistics",
        "graph_edge_stats": "Edge Statistics",
        "graph_type": "Type", "graph_count": "Count",
        "graph_total_nodes": "Total nodes: {n}",
        "graph_total_edges": "Total edges: {n}",
        "graph_communities_n": "Communities: {n} (Leiden clustering)",
        "graph_top_callers": "Top Callers",
        "graph_function": "Function", "graph_file": "File", "graph_calls": "Calls",
        "graph_code_graph": "Code Graph",
        "graph_query_fail": "Query failed or no results",
        "graph_processes": "Processes ({n})",
        "graph_proc_id": "ID", "graph_proc_summary": "Summary",
        "graph_proc_steps": "Steps", "graph_proc_type": "Type",
        "graph_definitions": "Definitions ({n})",
        "graph_def_name": "Name", "graph_def_line": "Line",
        "graph_proc_symbols": "Process Symbols ({n})",
        "graph_sym_module": "Module", "graph_sym_process": "Process",
        "graph_no_results": "No matching results",
        "graph_n_results": "{n} results total",
        "graph_cross_deps": "Cross-module Dependencies (CALLS)",
        "graph_caller": "Caller", "graph_callee": "Callee",
        "graph_no_cross_calls": "No cross-module call edges",
        "graph_n_cross_calls": "{n} cross-file call relations",
        "graph_leiden_community": "Leiden Communities",
        "graph_no_community": "No community data",
        "graph_comm_id": "ID", "graph_comm_domain": "Domain",
        "graph_comm_symbols": "Symbols", "graph_comm_cohesion": "Cohesion",
        "graph_comm_members": "Members (sampled)",
        "graph_n_communities": "{n} communities total",
        "graph_module_dist": "Module File Distribution",
        "graph_module": "Module", "graph_files": "Files",
        "graph_pct": "Pct", "graph_no_files": "No file nodes",
        "graph_n_files_modules": "{files} files, {modules} modules total",
        "graph_hub_nodes": "Hub Nodes",
        "graph_symbol": "Symbol", "graph_refs": "Refs",
        "graph_no_data": "No data",
        "graph_n_hubs": "{n} high-reference symbols",
        "graph_hierarchy": "Class Hierarchy",
        "graph_no_hierarchy": "No class inheritance found",
        "graph_n_subclasses": "{n} subclasses",
        "graph_n_inherit": "{edges} inheritance relations, {bases} base classes",
        "graph_generating": "Generating code graph: {name}",
        # watch
        "watch_ft": "Refresh every {n}s | Took {t:.1f}s | Ctrl+C to exit",
    },
    "zh": {
        "just_now": "刚刚", "secs_ago": "{n}秒前", "mins_ago": "{n}分钟前",
        "hours_ago": "{n}小时前", "days_ago": "{n}天前", "months_ago": "{n}月前",
        "years_ago": "{n}年前", "no_commits": "无提交",
        "col_name": "名称", "col_branch": "分支", "col_last_commit": "最后提交",
        "col_status": "状态", "col_language": "语言", "col_commits": "提交数",
        "col_remote": "远程", "dashboard_sub": "● = 未提交变更  ✓ = 干净",
        "col_time": "时间", "col_repo": "仓库", "col_author": "作者", "col_message": "提交信息",
        "health_dirty": "  ⚠ 未提交变更", "health_ahead": "  ⚠ 未推送提交",
        "health_behind": "  ⚠ 落后远程", "health_no_remote": "  ○ 无远程仓库",
        "health_inactive": "  ○ 长期未活跃 >30天", "health_ok": "  ✓ 一切正常",
        "lbl_path": "路径", "lbl_remote": "远程", "lbl_branch": "分支", "lbl_tags": "标签",
        "lbl_commits": "提交", "lbl_contribs": "贡献者", "lbl_lang": "语言",
        "lbl_status": "状态", "lbl_recent": "最近提交", "lbl_activity": "活跃度",
        "none": "无", "this_week": "本周", "this_month": "本月",
        "total_repos": "总仓库", "active_30d": "活跃(30天)", "has_remote": "有远程",
        "total_commits": "总提交", "lang_dist": "语言分布",
        "week_top": "本周活跃 Top", "remote_dist": "远程分布",
        "all_clean": "所有仓库都是干净的", "col_changes": "变更",
        "dirty_title": "有未提交变更的仓库 ({n})",
        "dirty_prompt": "输入序号用 lazygit 打开，直接回车退出",
        "invalid_num": "无效序号",
        "processing_n": "逐个处理 {n} 个有变更的仓库",
        "each_hint": "关闭 lazygit 后自动跳到下一个，Ctrl+C 退出",
        "interrupted": "已中断", "all_done": "全部处理完毕",
        "no_remote_repos": "没有配置远程仓库的项目",
        "pull_prep": "准备 pull {n} 个有远程的仓库",
        "updated_n": "  ✓ 已更新 ({n})", "failed_n": "  ✗ 失败 ({n})",
        "up_to_date_n": "  ─ 已是最新 ({n})",
        "no_push_needed": "没有需要推送的仓库",
        "confirm_push": "确认推送以上 {n} 个仓库? [y/N]",
        "cancelled": "已取消", "push_done": "推送完成",
        "missing_msg": "缺少提交信息，请用 -m 指定",
        "tree_clean": "{name}: 工作区干净，无需提交",
        "n_changes": "{name} — {n} 个变更文件:",
        "n_more": "  ... 还有 {n} 个文件",
        "commit_msg_lbl": "提交信息", "confirm_commit": "确认 git add -A && commit? [y/N]",
        "committed": "✓ 已提交", "commit_fail": "✗ 提交失败:",
        "no_stash_needed": "{name}: 工作区干净，无需 stash",
        "stash_ok": "✓ {name}: stash 了 {n} 个变更", "stash_fail": "✗ stash 失败:",
        "stash_pop_ok": "✓ {name}: stash pop 成功", "stash_pop_fail": "✗ stash pop 失败:",
        "no_match": "未找到匹配: {pattern}",
        "multi_match": "多个匹配: {hints}",
        "match_hint": "提示: 用完整路径区分",
        "repo_not_found": "未找到仓库: {name}",
        "lazygit_missing": "未安装 lazygit", "gitnexus_missing": "未找到 gitnexus",
        "expected_path": "期望路径: {path}",
        "gen_doc": "生成文档: {name}", "cannot_scan": "无法扫描: {name}",
        "doc_ok": "✓ 已生成: {path}", "doc_stats": "{imgs} 张图表 | {commits} 条提交记录",
        "copying": "复制: {path}",
        "doc_none": "无",
        "doc_clean": "干净", "doc_dirty": "{n} 未提交变更",
        "doc_info": "基本信息", "doc_attr": "属性", "doc_value": "值",
        "doc_path": "路径", "doc_remote": "远程", "doc_branch": "分支",
        "doc_language": "语言", "doc_commits_week_month": "**{commits}** commits (本周 {week} / 本月 {month})",
        "doc_contribs": "贡献者", "doc_tags": "标签",
        "doc_status": "状态",
        "doc_overview": "项目概述",
        "doc_arch": "架构",
        "doc_arch_full": "完整架构详见 CLAUDE.md ({n} 行)",
        "doc_diagrams": "关键图表", "doc_source_tree": "源码结构",
        "doc_docs_index": "文档索引", "doc_recent": "最近活动",
        "rpt_title": "代码图谱",
        "rpt_info": "数据来源",
        "rpt_gen_by": "由 [GitNexus](https://github.com/nicobailon/gitnexus) 知识图谱引擎自动生成。",
        "rpt_regen": "重新生成: `cb graph {name} report`",
        "rpt_metric": "指标", "rpt_value": "值",
        "rpt_nodes": "节点", "rpt_edges": "边",
        "rpt_communities_label": "社区",
        "rpt_processes_label": "流程", "rpt_files_label": "文件",
        "rpt_idx_time": "索引时间",
        "rpt_related": "相关文档: [[{name}]]",
        "rpt_overview": "图谱总览",
        "rpt_overview_desc": "知识图谱包含 **{nodes:,}** 个节点和 **{edges:,}** 条边，覆盖 {files} 个源文件。",
        "rpt_node_top3": "节点主要由 {top3} 组成。",
        "rpt_node_dist": "节点类型分布",
        "rpt_edge_dist": "边类型分布",
        "rpt_module_dist": "模块文件分布",
        "rpt_pie_title": "文件数按模块",
        "rpt_module": "模块", "rpt_file_count": "文件数", "rpt_pct": "占比",
        "rpt_cross_deps": "跨模块依赖 (热点调用)",
        "rpt_cross_desc": "文件间 CALLS 调用边按频次排名，反映模块间耦合关系:",
        "rpt_caller_file": "调用方文件", "rpt_callee_file": "被调用文件", "rpt_call_count": "调用次数",
        "rpt_imports": "模块间导入关系",
        "rpt_hubs": "高引用度符号 (Hub Nodes)",
        "rpt_hubs_desc": "被其他符号引用次数最多的函数和类，是代码库的**核心 API**:",
        "rpt_symbol": "符号", "rpt_file": "文件", "rpt_refs": "引用次数", "rpt_type": "类型",
        "rpt_top_callers": "顶级调用者 (Top Callers)",
        "rpt_top_callers_desc": "主动调用其他函数次数最多的符号，通常是**入口函数或核心调度器**:",
        "rpt_function": "函数", "rpt_call_n": "调用次数",
        "rpt_proc_flows": "执行流程 (Process Flows)",
        "rpt_proc_desc": "GitNexus 通过调用链追踪检测到 **{n}** 条执行流程。以下为最重要的 {m} 条:",
        "rpt_file_index": "关键文件索引",
        "rpt_file_index_desc": "AI 导航指南：按文件定义的符号数排列，快速了解每个文件的职责。",
        "rpt_file_col": "文件", "rpt_sym_count": "符号数", "rpt_main_defs": "主要定义",
        "rpt_inherit": "类继承体系",
        "rpt_inherit_desc": "{n} 条继承关系，{m} 个基类:",
        "rpt_parent": "基类", "rpt_child": "子类",
        "rpt_structs": "核心数据结构 (Struct)",
        "rpt_structs_desc": "共索引到 {n} 个 Struct，按模块分布:",
        "rpt_enums": "枚举类型 (Enum)",
        "rpt_namespaces": "命名空间结构",
        "rpt_community_struct": "社区结构 (Leiden Clustering)",
        "rpt_community_desc": "Leiden 算法检测到 **{n}** 个社区，以下为符号数最多的社区:",
        "rpt_involved_files": "涉及文件",
        "rpt_core_symbols": "核心符号",
        "rpt_comm_overview": "社区总览",
        "rpt_comm_col": "社区", "rpt_domain": "域",
        "rpt_sym_n": "符号数", "rpt_cohesion": "凝聚度",
        "rpt_edge_stats": "边关系统计",
        "rpt_edge_type": "边类型", "rpt_meaning": "含义", "rpt_count": "数量",
        "rpt_edge_calls": "函数调用", "rpt_edge_defines": "文件定义符号",
        "rpt_edge_imports": "文件/模块导入", "rpt_edge_contains": "目录包含文件",
        "rpt_edge_member": "命名空间成员", "rpt_edge_step": "流程步骤",
        "rpt_edge_extends": "类继承",
        "rpt_code_graph_doc": "代码图谱",
        "rpt_xref_label": "GitNexus 代码图谱",
        "graph_ok": "✓ 已生成: {path}",
        "graph_stats": "{nodes:,} 节点 | {edges:,} 边 | {communities} 社区 | {processes} 流程",
        "xref_added": "  已添加交叉引用到 {name}.md",
        "graph_specify_repo": "请指定仓库名称",
        "graph_already_indexed": "⟳ {name} 已有索引，将重新构建",
        "graph_cpp_warn": "⚠ C/C++ 项目索引可能耗时较长或不稳定",
        "graph_indexing": "索引: {name}",
        "graph_index_ok": "✓ 索引完成: {name}",
        "graph_index_fail": "✗ 索引失败 (exit {code})",
        "graph_index_timeout": "✗ 索引超时 (>180s)",
        "graph_not_indexed": "尚未建立图索引，请先运行: cb graph {name} index",
        "graph_idx_time": "索引时间: {time}",
        "graph_unknown": "未知",
        "graph_node_stats": "节点统计",
        "graph_edge_stats": "边统计",
        "graph_type": "类型", "graph_count": "数量",
        "graph_total_nodes": "总节点: {n}",
        "graph_total_edges": "总边: {n}",
        "graph_communities_n": "社区数: {n} (Leiden 聚类)",
        "graph_top_callers": "Top 调用者",
        "graph_function": "函数", "graph_file": "文件", "graph_calls": "调用数",
        "graph_code_graph": "代码图谱",
        "graph_query_fail": "查询失败或无结果",
        "graph_processes": "执行流 ({n})",
        "graph_proc_id": "ID", "graph_proc_summary": "摘要",
        "graph_proc_steps": "步数", "graph_proc_type": "类型",
        "graph_definitions": "符号定义 ({n})",
        "graph_def_name": "名称", "graph_def_line": "行号",
        "graph_proc_symbols": "流程符号 ({n})",
        "graph_sym_module": "模块", "graph_sym_process": "流程",
        "graph_no_results": "无匹配结果",
        "graph_n_results": "共 {n} 条结果",
        "graph_cross_deps": "跨模块依赖 (CALLS)",
        "graph_caller": "调用方", "graph_callee": "被调用方",
        "graph_no_cross_calls": "无跨模块调用边",
        "graph_n_cross_calls": "{n} 条跨文件调用关系",
        "graph_leiden_community": "Leiden 社区",
        "graph_no_community": "无社区数据",
        "graph_comm_id": "ID", "graph_comm_domain": "域",
        "graph_comm_symbols": "符号数", "graph_comm_cohesion": "凝聚度",
        "graph_comm_members": "成员 (采样)",
        "graph_n_communities": "共 {n} 个社区",
        "graph_module_dist": "模块文件分布",
        "graph_module": "模块", "graph_files": "文件数",
        "graph_pct": "占比", "graph_no_files": "无文件节点",
        "graph_n_files_modules": "共 {files} 个文件, {modules} 个模块",
        "graph_hub_nodes": "Hub Nodes",
        "graph_symbol": "符号", "graph_refs": "引用数",
        "graph_no_data": "无数据",
        "graph_n_hubs": "{n} 个高引用符号",
        "graph_hierarchy": "类继承",
        "graph_no_hierarchy": "无类继承关系",
        "graph_n_subclasses": "{n} 子类",
        "graph_n_inherit": "{edges} 条继承关系, {bases} 个基类",
        "graph_generating": "生成代码图谱: {name}",
        "watch_ft": "每 {n}s 刷新 | 耗时 {t:.1f}s | Ctrl+C 退出",
    },
}

_ui_lang = CFG["lang"]  # "auto", "en", or "zh"


def _detect_lang() -> str:
    loc = locale.getdefaultlocale()[0] or ""
    return "zh" if loc.startswith("zh") else "en"


def T(key: str, **kw) -> str:
    """Get translated UI string."""
    lang = _ui_lang if _ui_lang != "auto" else _detect_lang()
    table = _I18N.get(lang, _I18N["en"])
    s = table.get(key, _I18N["en"].get(key, key))
    return s.format(**kw) if kw else s


console = Console()

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
    """Convert datetime to human-readable relative time."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return T("just_now")
    if seconds < 60:
        return T("secs_ago", n=seconds)
    minutes = seconds // 60
    if minutes < 60:
        return T("mins_ago", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return T("hours_ago", n=hours)
    days = hours // 24
    if days < 30:
        return T("days_ago", n=days)
    months = days // 30
    if months < 12:
        return T("months_ago", n=months)
    years = days // 365
    return T("years_ago", n=years)


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
        "last_time_rel": relative_time(last_time) if last_time else T("no_commits"),
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
    table.add_column(T("col_name"), style="bold cyan", no_wrap=True, max_width=20)
    table.add_column(T("col_branch"), style="magenta", no_wrap=True, max_width=15)
    table.add_column(T("col_last_commit"), no_wrap=True, max_width=10)
    table.add_column(T("col_status"), no_wrap=True, justify="center")
    table.add_column(T("col_language"), no_wrap=True, max_width=12)
    table.add_column(T("col_commits"), justify="right")
    table.add_column(T("col_remote"), no_wrap=True)

    for r in repos:
        # Color based on timestamp, not by parsing the relative time string
        rel = r["last_time_rel"]
        ts = r["last_time_ts"]
        if ts == 0:
            time_text = Text(T("no_commits"), style="dim")
        else:
            age_days = (time.time() - ts) / 86400
            if age_days < 1:
                time_text = Text(rel, style="green")
            elif age_days <= 7:
                time_text = Text(rel, style="green")
            elif age_days <= 30:
                time_text = Text(rel, style="yellow")
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
    panel = Panel(table, title=title, subtitle=T("dashboard_sub"), border_style="blue")
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
    table.add_column(T("col_time"), style="dim", no_wrap=True, max_width=10)
    table.add_column(T("col_repo"), style="bold cyan", no_wrap=True, max_width=20)
    table.add_column(T("col_author"), style="magenta", no_wrap=True, max_width=12)
    table.add_column(T("col_message"), max_width=60)

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
            (T("health_dirty"), "bold yellow"),
            (f" ({len(dirty_repos)} repos)\n", "yellow"),
            (f"    {items}\n", ""),
        ))

    if ahead_repos:
        items = " | ".join(f"{r['name']} (↑{r['ahead']})" for r in ahead_repos)
        lines.append(Text.assemble(
            (T("health_ahead"), "bold yellow"),
            (f" ({len(ahead_repos)} repos)\n", "yellow"),
            (f"    {items}\n", ""),
        ))

    if behind_repos:
        items = " | ".join(f"{r['name']} (↓{r['behind']})" for r in behind_repos)
        lines.append(Text.assemble(
            (T("health_behind"), "bold red"),
            (f" ({len(behind_repos)} repos)\n", "red"),
            (f"    {items}\n", ""),
        ))

    if no_remote:
        items = " | ".join(r["name"] for r in no_remote)
        lines.append(Text.assemble(
            (T("health_no_remote"), "bold dim"),
            (f" ({len(no_remote)} repos)\n", "dim"),
            (f"    {items}\n", ""),
        ))

    if inactive:
        items = " | ".join(f"{r['name']} ({r['last_time_rel']})" for r in inactive)
        lines.append(Text.assemble(
            (T("health_inactive"), "bold dim"),
            (f" ({len(inactive)} repos)\n", "dim"),
            (f"    {items}\n", ""),
        ))

    if clean:
        lines.append(Text.assemble(
            (T("health_ok"), "bold green"),
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
        console.print(f"[red]{T('cannot_scan', name=repo_name)}[/red]")
        return

    if args.json:
        info.pop("last_time", None)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    branches = run_git(repo_path, "branch", "--list").split("\n")
    branches = [b.strip().lstrip("* ") for b in branches if b.strip()]
    branch_count = len(branches)

    tags = run_git(repo_path, "tag", "--list").split("\n")
    tags = [t for t in tags if t.strip()]
    tag_count = len(tags)
    latest_tag = tags[-1] if tags else T("none")

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
    lp, lr, lb, lt, lc = T("lbl_path"), T("lbl_remote"), T("lbl_branch"), T("lbl_tags"), T("lbl_commits")
    lines.append(f"  [dim]{lp}:[/dim]     {repo_path}")
    lines.append(f"  [dim]{lr}:[/dim]     {info['remote_url'] or T('none')}")
    branch_extra = f" (+ {branch_count - 1} branches)" if branch_count > 1 else ""
    lines.append(f"  [dim]{lb}:[/dim]     [magenta]{info['branch']}[/magenta]{branch_extra}")
    lines.append(f"  [dim]{lt}:[/dim]     {tag_count} tags (latest: {latest_tag})")
    lines.append(f"  [dim]{lc}:[/dim]     {info['commits']} commits")

    if contributors:
        contribs_str = ", ".join(f"{name}({n})" for name, n in contributors[:5])
        lines.append(f"  [dim]{T('lbl_contribs')}:[/dim]   {len(contributors)} ({contribs_str})")

    if lang_detail:
        lang_str = " | ".join(
            f"{lang} {count * 100 // total_files}%" for lang, count in lang_detail[:5]
        )
        lines.append(f"  [dim]{T('lbl_lang')}:[/dim]     {lang_str}")

    status_parts = []
    if unstaged > 0:
        status_parts.append(f"{unstaged} modified")
    if staged > 0:
        status_parts.append(f"{staged} staged")
    if untracked > 0:
        status_parts.append(f"{untracked} untracked")
    if not status_parts:
        status_parts.append("[green]clean[/green]")
    lines.append(f"  [dim]{T('lbl_status')}:[/dim]     {', '.join(status_parts)}")

    lines.append("")
    lines.append(f"  [bold]{T('lbl_recent')}:[/bold]")
    for rel, msg in recent_commits:
        if len(msg) > 55:
            msg = msg[:52] + "..."
        lines.append(f"   [dim]{rel:>8}[/dim]  {msg}")

    lines.append("")
    max_bar = 12
    bar_filled = min(max_bar, month_n)
    bar = "█" * bar_filled + "░" * (max_bar - bar_filled)
    lines.append(f"  [dim]{T('lbl_activity')}:[/dim]   {bar} {T('this_week')} {week_n} | {T('this_month')} {month_n}")

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
    lines.append(f"  [bold]{T('total_repos')}:[/bold] {total}  |  [bold]{T('active_30d')}:[/bold] {active_30}  |  [bold]{T('has_remote')}:[/bold] {has_remote}")
    lines.append(f"  [bold]{T('total_commits')}:[/bold] {total_commits:,}  |  [bold]{T('this_month')}:[/bold] {month_commits}  |  [bold]{T('this_week')}:[/bold] {week_commits}")
    lines.append("")

    lang_counter = Counter()
    for r in repos:
        if r["lang"] and r["lang"] != "-":
            lang_counter[r["lang"]] += 1

    if lang_counter:
        lines.append(f"  [bold]{T('lang_dist')}:[/bold]")
        max_count = lang_counter.most_common(1)[0][1]
        bar_width = 20
        for lang, count in lang_counter.most_common(10):
            bar_len = max(1, count * bar_width // max_count)
            bar = "█" * bar_len + "░" * (bar_width - bar_len)
            lines.append(f"   {lang:<12} {bar} {count:>2} repos")
        lines.append("")

    top_week = sorted(week_per_repo.items(), key=lambda x: x[1], reverse=True)
    top_week = [(name, n) for name, n in top_week if n > 0][:8]
    if top_week:
        lines.append(f"  [bold]{T('week_top')}:[/bold]")
        items = " | ".join(f"[cyan]{name}[/cyan]({n})" for name, n in top_week)
        lines.append(f"   {items}")
        lines.append("")

    remote_counter = Counter(r["remote_type"] for r in repos)
    if remote_counter:
        lines.append(f"  [bold]{T('remote_dist')}:[/bold]")
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
        console.print(f"[yellow]{T('multi_match', hints=', '.join(hints))}[/yellow]")
        console.print(f"[dim]{T('match_hint')}[/dim]")
        return None
    console.print(f"[red]{T('repo_not_found', name=name)}[/red]")
    return None


def require_lazygit() -> str | None:
    """Check if lazygit is available, return path."""
    path = shutil.which("lazygit")
    if not path:
        console.print(f"[red]{T('lazygit_missing')}[/red]  brew install lazygit")
    return path


def require_gitnexus() -> str | None:
    """Check if gitnexus is available, return path."""
    path = shutil.which("gitnexus") or (GITNEXUS_BIN if GITNEXUS_BIN and Path(GITNEXUS_BIN).is_file() else None)
    if not path:
        console.print(f"[red]{T('gitnexus_missing')}[/red]  npm install -g gitnexus")
        if GITNEXUS_BIN:
            console.print(f"[dim]{T('expected_path', path=GITNEXUS_BIN)}[/dim]")
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
        console.print(f"[green]{T('all_clean')}[/green]")
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column(T("col_repo"), style="bold cyan", no_wrap=True)
    table.add_column(T("col_changes"), style="yellow", justify="right")
    table.add_column(T("col_branch"), style="magenta")
    table.add_column(T("col_last_commit"), style="dim")

    for i, r in enumerate(dirty, 1):
        table.add_row(str(i), r["name"], str(r["dirty"]), r["branch"], r["last_time_rel"])

    panel = Panel(table, title=T("dirty_title", n=len(dirty)), border_style="yellow")
    console.print(panel)
    console.print(f"[dim]{T('dirty_prompt')}[/dim]")

    try:
        choice = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not choice:
        return
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(dirty):
        console.print(f"[red]{T('invalid_num')}[/red]")
        return

    repo = dirty[int(choice) - 1]
    console.print(f"[dim]lazygit → {repo['name']}[/dim]")
    os.execvp(lg, [lg, "--path", repo["path"]])


def cmd_each(args):
    """Process dirty repos one by one with lazygit."""
    lg = require_lazygit()
    if not lg:
        return
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    dirty = sorted([r for r in repos if r["dirty"] > 0], key=lambda r: r["dirty"], reverse=True)

    if not dirty:
        console.print(f"[green]{T('all_clean')}[/green]")
        return

    console.print(f"[bold]{T('processing_n', n=len(dirty))}[/bold]")
    console.print(f"[dim]{T('each_hint')}[/dim]\n")

    for i, r in enumerate(dirty, 1):
        console.print(f"[cyan][{i}/{len(dirty)}][/cyan] {r['name']} [yellow](●{r['dirty']})[/yellow]")
        try:
            subprocess.run([lg, "--path", r["path"]])
        except KeyboardInterrupt:
            console.print(f"\n[dim]{T('interrupted')}[/dim]")
            return
    console.print(f"\n[green]{T('all_done')}[/green]")


def cmd_pull(args):
    """批量 git pull"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    targets = [r for r in repos if r["remote_type"] != "none"]

    if not targets:
        if args.json:
            print(json.dumps({"ok": [], "skip": [], "fail": []}, indent=2))
        else:
            console.print(f"[dim]{T('no_remote_repos')}[/dim]")
        return

    if not args.json:
        console.print(f"[bold]{T('pull_prep', n=len(targets))}[/bold]\n")

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
        console.print(f"[green]{T('updated_n', n=len(results['ok']))}[/green]")
        for r, msg in sorted(results["ok"], key=lambda x: x[0]["name"]):
            console.print(f"    [cyan]{r['name']}[/cyan] {msg}")

    if results["fail"]:
        console.print(f"[red]{T('failed_n', n=len(results['fail']))}[/red]")
        for r, msg in sorted(results["fail"], key=lambda x: x[0]["name"]):
            console.print(f"    [cyan]{r['name']}[/cyan] [dim]{msg}[/dim]")

    skipped = len(results["skip"])
    if skipped:
        console.print(f"[dim]{T('up_to_date_n', n=skipped)}[/dim]")


def cmd_push(args):
    """推送所有有 ahead 提交的仓库"""
    code_dir = Path(args.path).expanduser()
    repos = scan_all(code_dir, full=False, filter_kw=args.filter)
    targets = [r for r in repos if r["ahead"] > 0]

    if not targets:
        console.print(f"[green]{T('no_push_needed')}[/green]")
        return

    targets.sort(key=lambda r: r["ahead"], reverse=True)

    if args.json:
        print(json.dumps([{"name": r["name"], "ahead": r["ahead"]} for r in targets], ensure_ascii=False, indent=2))
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column(T("col_repo"), style="bold cyan")
    table.add_column(T("col_branch"), style="magenta")
    table.add_column("Ahead", style="yellow", justify="right")
    table.add_column(T("col_remote"), style="dim")

    for r in targets:
        table.add_row(r["name"], r["branch"], f"↑{r['ahead']}", r["remote_type"])

    console.print(table)
    console.print(f"\n[bold]{T('confirm_push', n=len(targets))}[/bold]")
    try:
        choice = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice not in ("y", "yes"):
        console.print(f"[dim]{T('cancelled')}[/dim]")
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

    console.print(f"\n[green]{T('push_done')}[/green]")


def cmd_commit(args):
    """快速 commit 指定仓库"""
    code_dir = Path(args.path).expanduser()
    repo_path = find_repo(code_dir, args.repo)
    if not repo_path:
        return

    message = args.message
    if not message:
        console.print(f"[red]{T('missing_msg')}[/red]")
        return

    status = run_git(repo_path, "status", "--porcelain")
    if not status:
        console.print(f"[green]{T('tree_clean', name=repo_path.name)}[/green]")
        return

    lines = status.split("\n")
    console.print(f"[bold]{T('n_changes', name=repo_path.name, n=len(lines))}[/bold]")
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
        console.print(f"  [dim]{T('n_more', n=len(lines) - 10)}[/dim]")

    if not args.yes:
        console.print(f'\n[bold]{T("commit_msg_lbl")}:[/bold] "{message}"')
        console.print(f"[bold]{T('confirm_commit')}[/bold]")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if choice not in ("y", "yes"):
            console.print(f"[dim]{T('cancelled')}[/dim]")
            return

    run_git(repo_path, "add", "-A")
    result = subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", message],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        console.print(f"[green]{T('committed')}[/green]")
    else:
        console.print(f"[red]{T('commit_fail')}[/red] {result.stderr.strip()}")


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
            console.print(f"[green]{T('no_stash_needed', name=repo_path.name)}[/green]")
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
            console.print(f"[green]{T('stash_ok', name=repo_path.name, n=dirty_n)}[/green]")
        else:
            console.print(f"[red]{T('stash_fail')}[/red] {result.stderr.strip()}")

    elif action == "pop":
        result = subprocess.run(
            ["git", "-C", str(repo_path), "stash", "pop"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            console.print(f"[green]{T('stash_pop_ok', name=repo_path.name)}[/green]")
        else:
            console.print(f"[red]{T('stash_pop_fail')}[/red] {result.stderr.strip()}")

    elif action == "list":
        out = run_git(repo_path, "stash", "list")
        if out:
            console.print(f"[bold]{repo_path.name} stash list:[/bold]")
            for line in out.split("\n"):
                console.print(f"  {line}")
        else:
            console.print(f"[dim]{repo_path.name}: no stash[/dim]")


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
        console.print(f"[dim]{T('no_match', pattern=pattern)}[/dim]")
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
            console.print(f"  [dim]... {len(lines) - 8} more[/dim]")

    console.print(f"\n[dim]{len(all_results)} repos, {total_matches} matches[/dim]")


# ---------------------------------------------------------------------------
# graph 命令 - GitNexus 代码图谱分析
# ---------------------------------------------------------------------------

def _parse_md_table(raw: str) -> list[list[str]]:
    """解析 gitnexus cypher 返回的 markdown 表格 (JSON 包裹), 返回数据行 (跳过表头和分隔行)"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
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


def _bar_chart_text(items: list[tuple[str, int]], max_width: int = 20) -> str:
    """生成文本柱状图行, 如 'Function   850 ███████████'"""
    if not items:
        return ""
    max_val = max(v for _, v in items) or 1
    max_label = max(len(label) for label, _ in items)
    lines = []
    for label, val in items:
        bar_len = val * max_width // max_val or (1 if val > 0 else 0)
        lines.append(f"    {label:<{max_label}}  {val:>6} {'█' * bar_len}")
    return "\n".join(lines)


def _module_prefix(filepath: str) -> str:
    """提取文件路径首段目录: 'include/foo/bar.hpp' → 'include'"""
    if not filepath:
        return "(root)"
    parts = filepath.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def _graph_require(args) -> tuple[str, Path, str] | None:
    """graph 子命令公共前置: 返回 (gitnexus路径, 仓库路径, 仓库名) 或 None"""
    gn = require_gitnexus()
    if not gn:
        return None
    code_dir = Path(args.path).expanduser()
    repo_name = getattr(args, "repo", None)
    if not repo_name:
        console.print(f"[red]{T('graph_specify_repo')}[/red]")
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
        console.print(f"[yellow]{T('graph_already_indexed', name=repo_name)}[/yellow]")

    info = scan_repo(repo_path, full=True)
    if info and info.get("lang") in ("C++", "C", "C/C++"):
        console.print(f"[yellow]{T('graph_cpp_warn')}[/yellow]")

    console.print(f"[bold]{T('graph_indexing', name=repo_name)}[/bold] → {repo_path}\n")
    try:
        r = subprocess.run([gn, "analyze", str(repo_path)], timeout=180)
        if r.returncode == 0:
            console.print(f"\n[green]{T('graph_index_ok', name=repo_name)}[/green]")
        else:
            console.print(f"\n[red]{T('graph_index_fail', code=r.returncode)}[/red]")
    except subprocess.TimeoutExpired:
        console.print(f"\n[red]{T('graph_index_timeout')}[/red]")
    except KeyboardInterrupt:
        console.print(f"\n[yellow]{T('interrupted')}[/yellow]")


def cmd_graph_overview(args):
    """显示仓库图谱概览"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    gn_dir = repo_path / ".gitnexus"
    try:
        mtime = datetime.fromtimestamp(gn_dir.stat().st_mtime)
        idx_time = relative_time(mtime)
    except Exception:
        idx_time = T("graph_unknown")

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

    parts = []
    parts.append(f"[dim]{T('graph_idx_time', time=idx_time)}[/dim]\n")

    if ok1:
        rows = _parse_md_table(out1)
        if rows:
            tbl = Table(title=T("graph_node_stats"), box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column(T("graph_type"), style="cyan", no_wrap=True)
            tbl.add_column(T("graph_count"), style="bold", justify="right")
            total = 0
            for r in rows:
                tbl.add_row(r[0], r[1])
                total += int(r[1]) if r[1].isdigit() else 0
            parts.append(tbl)
            parts.append(f"[dim]{T('graph_total_nodes', n=total)}[/dim]\n")

    if ok2:
        rows = _parse_md_table(out2)
        if rows:
            tbl = Table(title=T("graph_edge_stats"), box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column(T("graph_type"), style="magenta", no_wrap=True)
            tbl.add_column(T("graph_count"), style="bold", justify="right")
            total_edges = 0
            for r in rows:
                tbl.add_row(r[0], r[1])
                total_edges += int(r[1]) if r[1].isdigit() else 0
            parts.append(tbl)
            parts.append(f"[dim]{T('graph_total_edges', n=total_edges)}[/dim]\n")

    if ok3:
        rows = _parse_md_table(out3)
        if rows and rows[0]:
            parts.append(f"[bold]{T('graph_communities_n', n=rows[0][0])}[/bold]\n")

    if ok4:
        rows = _parse_md_table(out4)
        if rows:
            tbl = Table(title=T("graph_top_callers"), box=box.SIMPLE, show_header=True, padding=(0, 1))
            tbl.add_column(T("graph_function"), style="bold cyan", no_wrap=True)
            tbl.add_column(T("graph_file"), style="dim")
            tbl.add_column(T("graph_calls"), style="bold yellow", justify="right")
            for r in rows:
                if len(r) >= 3:
                    tbl.add_row(r[0], r[1], r[2])
            parts.append(tbl)

    from rich.console import Group
    panel = Panel(Group(*parts), title=f"[bold]{repo_name}[/bold] — {T('graph_code_graph')}", border_style="blue")
    console.print(panel)


def cmd_graph_query(args):
    """搜索图谱中的符号"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    keywords = args.keywords
    ok, out = run_gitnexus(gn, "query", keywords, "--repo", repo_name)
    if not ok or not out:
        console.print(f"[red]{T('graph_query_fail')}[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        console.print(out)
        return

    processes = data.get("processes", [])
    if processes:
        tbl = Table(title=T("graph_processes", n=len(processes)), box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column(T("graph_proc_id"), style="dim", no_wrap=True)
        tbl.add_column(T("graph_proc_summary"), style="bold cyan")
        tbl.add_column(T("graph_proc_steps"), justify="right")
        tbl.add_column(T("graph_proc_type"), style="magenta")
        for p in processes[:15]:
            tbl.add_row(
                p.get("id", ""),
                p.get("summary", ""),
                str(p.get("step_count", "")),
                p.get("process_type", ""),
            )
        console.print(tbl)

    defs = data.get("definitions", [])
    if defs:
        tbl = Table(title=T("graph_definitions", n=len(defs)), box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column(T("graph_def_name"), style="bold cyan", no_wrap=True)
        tbl.add_column(T("graph_file"), style="dim")
        tbl.add_column(T("graph_def_line"), style="yellow", justify="right")
        for d in defs[:20]:
            name = d.get("name", "")
            fpath = d.get("filePath", "")
            line = str(d.get("startLine", ""))
            tbl.add_row(name, fpath, line)
        console.print(tbl)

    syms = data.get("process_symbols", [])
    if syms:
        tbl = Table(title=T("graph_proc_symbols", n=len(syms)), box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column(T("graph_def_name"), style="bold cyan", no_wrap=True)
        tbl.add_column(T("graph_file"), style="dim")
        tbl.add_column(T("graph_sym_module"), style="magenta")
        tbl.add_column(T("graph_sym_process"), style="dim")
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
        console.print(f"[dim]{T('graph_no_results')}[/dim]")
    else:
        console.print(f"\n[dim]{T('graph_n_results', n=total)}[/dim]")


def cmd_graph_deps(args):
    """显示跨模块依赖图"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    ok, out = run_gitnexus(gn, "cypher",
        "MATCH (a:Function)-[r:CodeRelation {type: 'CALLS'}]->(b) "
        "WHERE a.filePath <> b.filePath "
        "RETURN a.filePath, b.filePath, count(*) AS weight "
        "ORDER BY weight DESC LIMIT 30",
        "--repo", repo_name)

    if not ok or not out:
        console.print(f"[red]{T('graph_query_fail')}[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    tbl = Table(title=f"{repo_name} — {T('graph_cross_deps')}", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column(T("graph_caller"), style="bold cyan")
    tbl.add_column("→", style="dim", no_wrap=True)
    tbl.add_column(T("graph_callee"), style="bold green")
    tbl.add_column(T("graph_calls"), style="yellow", justify="right")

    rows = _parse_md_table(out)
    for r in rows:
        if len(r) >= 3:
            tbl.add_row(r[0], "→", r[1], r[2])

    if not rows:
        console.print(f"[dim]{T('graph_no_cross_calls')}[/dim]")
    else:
        console.print(tbl)
        console.print(f"\n[dim]{T('graph_n_cross_calls', n=len(rows))}[/dim]")


def cmd_graph_community(args):
    """显示 Leiden 社区结构"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result

    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    ok, out = run_gitnexus(gn, "cypher",
        "MATCH (c:Community) RETURN c.id, c.label, c.symbolCount, c.cohesion "
        "ORDER BY c.symbolCount DESC",
        "--repo", repo_name)

    if not ok or not out:
        console.print(f"[red]{T('graph_query_fail')}[/red]")
        return

    if getattr(args, "json", False):
        print(out)
        return

    communities = _parse_md_table(out)

    if not communities:
        console.print(f"[dim]{T('graph_no_community')}[/dim]")
        return
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

    tbl = Table(title=f"{repo_name} — {T('graph_leiden_community')}", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column(T("graph_comm_id"), style="dim", no_wrap=True)
    tbl.add_column(T("graph_comm_domain"), style="magenta", no_wrap=True)
    tbl.add_column(T("graph_comm_symbols"), style="bold yellow", justify="right")
    tbl.add_column(T("graph_comm_cohesion"), style="cyan", justify="right")
    tbl.add_column(T("graph_comm_members"), style="dim")

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
    console.print(f"\n[dim]{T('graph_n_communities', n=len(communities))}[/dim]")


def cmd_graph_modules(args):
    """显示模块文件分布"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result
    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return
    ok, out = run_gitnexus(gn, "cypher", "MATCH (f:File) RETURN f.filePath AS path", "--repo", repo_name)
    if not ok or not out:
        console.print(f"[red]{T('graph_query_fail')}[/red]")
        return
    if getattr(args, "json", False):
        print(out)
        return
    rows = _parse_md_table(out)
    if not rows:
        console.print(f"[dim]{T('graph_no_files')}[/dim]")
        return
    counter = Counter()
    for r in rows:
        if r:
            counter[_module_prefix(r[0])] += 1
    total = sum(counter.values())
    sorted_mods = counter.most_common()
    tbl = Table(title=f"{repo_name} — {T('graph_module_dist')}", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column(T("graph_module"), style="bold cyan", no_wrap=True)
    tbl.add_column(T("graph_files"), style="bold yellow", justify="right")
    tbl.add_column(T("graph_pct"), style="dim", justify="right")
    tbl.add_column("", style="green")
    max_count = sorted_mods[0][1] if sorted_mods else 1
    for mod, count in sorted_mods:
        pct = f"{count * 100 // total}%"
        bar = "█" * (count * 20 // max_count)
        tbl.add_row(mod, str(count), pct, bar)
    console.print(tbl)
    console.print(f"\n[dim]{T('graph_n_files_modules', files=total, modules=len(sorted_mods))}[/dim]")


def cmd_graph_hubs(args):
    """显示高引用度符号"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result
    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    def _query_hubs(label):
        return run_gitnexus(gn, "cypher",
            f"MATCH (a)-[r:CodeRelation]->(b:{label}) "
            f"RETURN b.name AS symbol, b.filePath AS file, count(*) AS refs "
            f"ORDER BY refs DESC LIMIT 15",
            "--repo", repo_name)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_fn = pool.submit(_query_hubs, "Function")
        fut_cls = pool.submit(_query_hubs, "Class")
        ok_fn, out_fn = fut_fn.result()
        ok_cls, out_cls = fut_cls.result()

    if getattr(args, "json", False):
        print(json.dumps({"functions": out_fn, "classes": out_cls}, ensure_ascii=False))
        return

    tbl = Table(title=f"{repo_name} — {T('graph_hub_nodes')}", box=box.SIMPLE, show_header=True, padding=(0, 1))
    tbl.add_column(T("graph_symbol"), style="bold cyan", no_wrap=True)
    tbl.add_column(T("graph_file"), style="dim")
    tbl.add_column(T("graph_refs"), style="bold yellow", justify="right")
    tbl.add_column(T("graph_type"), style="magenta")
    count = 0
    for label, ok, out in [("Function", ok_fn, out_fn), ("Class", ok_cls, out_cls)]:
        if ok and out:
            for r in _parse_md_table(out):
                if len(r) >= 3:
                    tbl.add_row(r[0], r[1], r[2], label)
                    count += 1
    if count == 0:
        console.print(f"[dim]{T('graph_no_data')}[/dim]")
    else:
        console.print(tbl)
        console.print(f"\n[dim]{T('graph_n_hubs', n=count)}[/dim]")


def cmd_graph_hierarchy(args):
    """显示类继承关系"""
    from rich.tree import Tree as RichTree
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result
    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return
    ok, out = run_gitnexus(gn, "cypher",
        "MATCH (a:Class)-[r:CodeRelation {type: 'EXTENDS'}]->(b:Class) "
        "RETURN a.name AS child, b.name AS parent, a.filePath AS file",
        "--repo", repo_name)
    if not ok or not out:
        console.print(f"[red]{T('graph_query_fail')}[/red]")
        return
    if getattr(args, "json", False):
        print(out)
        return
    rows = _parse_md_table(out)
    if not rows:
        console.print(f"[dim]{T('graph_no_hierarchy')}[/dim]")
        return
    parent_map: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        if len(r) >= 3:
            parent_map.setdefault(r[1], []).append((r[0], r[2]))
    tree = RichTree(f"[bold]{repo_name}[/bold] — {T('graph_hierarchy')}", guide_style="dim")
    for parent, children in sorted(parent_map.items(), key=lambda x: -len(x[1])):
        branch = tree.add(f"[bold cyan]{parent}[/bold cyan] ({T('graph_n_subclasses', n=len(children))})")
        for child, fpath in children:
            branch.add(f"{child} [dim]{fpath}[/dim]")
    console.print(tree)
    console.print(f"\n[dim]{T('graph_n_inherit', edges=len(rows), bases=len(parent_map))}[/dim]")


def cmd_graph_report(args):
    """生成 Obsidian 代码图谱文档"""
    result = _graph_require(args)
    if not result:
        return
    gn, repo_path, repo_name = result
    if not is_graph_indexed(repo_path):
        console.print(f"[yellow]{T('graph_not_indexed', name=repo_name)}[/yellow]")
        return

    console.print(f"[bold]{T('graph_generating', name=repo_name)}[/bold]\n")

    # 索引时间
    gn_dir = repo_path / ".gitnexus"
    try:
        idx_time_str = datetime.fromtimestamp(gn_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        idx_time_str = T("graph_unknown")

    # 并行 Cypher 查询 — 18 条
    queries = {
        "nodes": "MATCH (n) RETURN labels(n) AS type, count(*) AS cnt ORDER BY cnt DESC",
        "edges": "MATCH ()-[r:CodeRelation]->() RETURN r.type AS edgeType, count(*) AS cnt ORDER BY cnt DESC",
        "communities": "MATCH (c:Community) RETURN c.id AS cid, c.label AS clabel, c.symbolCount AS symbols, c.cohesion AS coh ORDER BY c.symbolCount DESC LIMIT 20",
        "inheritance": "MATCH (a:Class)-[r:CodeRelation {type: 'EXTENDS'}]->(b:Class) RETURN a.name AS child, b.name AS parent, a.filePath AS file",
        "hub_fn": "MATCH (a)-[r:CodeRelation]->(b:Function) RETURN b.name AS symbol, b.filePath AS file, count(*) AS refs ORDER BY refs DESC LIMIT 20",
        "hub_class": "MATCH (a)-[r:CodeRelation]->(b:Class) RETURN b.name AS symbol, b.filePath AS file, count(*) AS refs ORDER BY refs DESC LIMIT 10",
        "files": "MATCH (f:File) RETURN f.filePath AS path",
        "namespaces": "MATCH (n:Namespace) RETURN DISTINCT n.name AS ns ORDER BY ns",
        "structs": "MATCH (s:Struct) RETURN s.name AS sname, s.filePath AS file ORDER BY s.name LIMIT 50",
        "processes": "MATCH (p:Process) RETURN count(*) AS n",
        "top_callers": "MATCH (a:Function)-[r:CodeRelation {type: 'CALLS'}]->(b) RETURN a.name AS caller, a.filePath AS file, count(*) AS calls ORDER BY calls DESC LIMIT 15",
        "cross_deps": "MATCH (a:Function)-[r:CodeRelation {type: 'CALLS'}]->(b:Function) WHERE a.filePath <> b.filePath RETURN a.filePath AS src, b.filePath AS dst, count(*) AS weight ORDER BY weight DESC LIMIT 20",
        "enums": "MATCH (e:Enum) RETURN e.name AS ename, e.filePath AS file ORDER BY e.name LIMIT 30",
        "imports": "MATCH (a:File)-[r:CodeRelation {type: 'IMPORTS'}]->(b:File) RETURN a.filePath AS src, b.filePath AS dst ORDER BY a.filePath LIMIT 40",
        "comm_count": "MATCH (c:Community) RETURN count(*) AS n",
        "proc_steps": "MATCH (s)-[r:CodeRelation {type: 'STEP_IN_PROCESS'}]->(p:Process) RETURN p.id, p.heuristicLabel, p.processType, p.stepCount, s.name, s.filePath, r.step ORDER BY p.stepCount DESC, p.id, r.step",
        "comm_members": "MATCH (s)-[r:CodeRelation {type: 'MEMBER_OF'}]->(c:Community) WHERE c.symbolCount >= 5 RETURN c.id, c.heuristicLabel, c.symbolCount, c.cohesion, s.name, labels(s)[0] AS kind, s.filePath ORDER BY c.symbolCount DESC, c.id, s.name LIMIT 300",
        "file_defs": "MATCH (f:File)-[r:CodeRelation {type: 'DEFINES'}]->(s) RETURN f.filePath AS file, s.name AS symbol, labels(s)[0] AS kind ORDER BY f.filePath, s.name LIMIT 500",
    }
    results: dict[str, list[list[str]]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(run_gitnexus, gn, "cypher", q, "--repo", repo_name): key
                   for key, q in queries.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            ok, out = fut.result()
            results[key] = _parse_md_table(out) if ok and out else []
            console.print(f"  [dim]✓ {key}[/dim]")

    # 数据提取
    node_data = [(r[0].strip("[]'\""), int(r[1])) for r in results.get("nodes", []) if len(r) >= 2 and r[1].isdigit()]
    edge_data = [(r[0], int(r[1])) for r in results.get("edges", []) if len(r) >= 2 and r[1].isdigit()]
    communities = results.get("communities", [])
    inheritance = results.get("inheritance", [])
    hub_fns = results.get("hub_fn", [])
    hub_classes = results.get("hub_class", [])
    file_paths = results.get("files", [])
    namespaces = [r[0] for r in results.get("namespaces", []) if r]
    structs = results.get("structs", [])
    enums = results.get("enums", [])
    proc_rows = results.get("processes", [])
    top_callers = results.get("top_callers", [])
    cross_deps = results.get("cross_deps", [])
    imports = results.get("imports", [])
    comm_count_rows = results.get("comm_count", [])

    # ── 新增: 流程步骤分组 (proc_steps) ──
    proc_step_rows = results.get("proc_steps", [])
    proc_groups: dict[str, dict] = {}  # p.id -> {label, type, stepCount, steps: [(name, file, step)]}
    for r in proc_step_rows:
        if len(r) >= 7:
            pid, plabel, ptype, psteps, sname, sfile, step_num = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            if pid not in proc_groups:
                proc_groups[pid] = {"label": plabel, "type": ptype, "stepCount": int(psteps) if psteps.isdigit() else 0, "steps": []}
            try:
                step_int = int(step_num)
            except (ValueError, TypeError):
                step_int = 999
            proc_groups[pid]["steps"].append((sname, sfile, step_int))
    # 排序: stepCount 降序, cross_community 优先
    for pg in proc_groups.values():
        pg["steps"].sort(key=lambda x: x[2])
    proc_sorted = sorted(proc_groups.items(), key=lambda x: (0 if x[1]["type"] == "cross_community" else 1, -x[1]["stepCount"]))

    # ── 新增: 社区成员分组 (comm_members) ──
    comm_member_rows = results.get("comm_members", [])
    comm_detail: dict[str, dict] = {}  # c.id -> {label, symbolCount, cohesion, members: [(name, kind, file)]}
    for r in comm_member_rows:
        if len(r) >= 7:
            cid, clabel, csymbols, ccoh, sname, skind, sfile = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            if cid not in comm_detail:
                comm_detail[cid] = {"label": clabel, "symbolCount": int(csymbols) if csymbols.isdigit() else 0, "cohesion": ccoh, "members": []}
            comm_detail[cid]["members"].append((sname, skind.strip("[]'\""), sfile))

    # ── 新增: 文件符号索引 (file_defs) ──
    file_def_rows = results.get("file_defs", [])
    file_def_map: dict[str, list[tuple[str, str]]] = {}  # file -> [(symbol, kind)]
    for r in file_def_rows:
        if len(r) >= 3:
            fpath, sym, kind = r[0], r[1], r[2].strip("[]'\"")
            file_def_map.setdefault(fpath, []).append((sym, kind))

    total_nodes = sum(v for _, v in node_data)
    total_edges = sum(v for _, v in edge_data)
    total_communities = int(comm_count_rows[0][0]) if comm_count_rows and comm_count_rows[0] else len(communities)
    n_processes = int(proc_rows[0][0]) if proc_rows and proc_rows[0] else 0
    total_files = len(file_paths)

    # 模块分布
    mod_counter = Counter()
    for r in file_paths:
        if r:
            mod_counter[_module_prefix(r[0])] += 1
    module_dist = mod_counter.most_common()

    # 检测主要语言 (用于上下文描述)
    lang = ""
    try:
        r = subprocess.run(["git", "-C", str(repo_path), "log", "-1", "--format=%s"], capture_output=True, text=True, timeout=5)
        # 用文件扩展名检测
        ext_counter: Counter = Counter()
        for row in file_paths:
            if row and "." in row[0]:
                ext_counter[row[0].rsplit(".", 1)[-1].lower()] += 1
        top_ext = ext_counter.most_common(3)
        ext_to_lang = {"py": "Python", "c": "C", "cpp": "C++", "h": "C/C++", "hpp": "C++",
                       "js": "JavaScript", "ts": "TypeScript", "go": "Go", "rs": "Rust", "java": "Java"}
        for ext, _ in top_ext:
            if ext in ext_to_lang:
                lang = ext_to_lang[ext]
                break
    except Exception:
        pass

    # ====== 组装 Markdown ======
    md = []
    md.append(f"# {repo_name} {T('rpt_title')}\n")
    md.append(f"> [!info] {T('rpt_info')}")
    md.append(f"> {T('rpt_gen_by')}")
    md.append(f"> {T('rpt_regen', name=repo_name)}")
    md.append(f">")
    md.append(f"> | {T('rpt_metric')} | {T('rpt_value')} |")
    md.append(f"> |------|-----|")
    md.append(f"> | {T('rpt_nodes')} | **{total_nodes:,}** |")
    md.append(f"> | {T('rpt_edges')} | **{total_edges:,}** |")
    md.append(f"> | {T('rpt_communities_label')} | **{total_communities}** (Leiden) |")
    md.append(f"> | {T('rpt_processes_label')} | **{n_processes}** |")
    md.append(f"> | {T('rpt_files_label')} | **{total_files}** |")
    md.append(f"> | {T('rpt_idx_time')} | {idx_time_str} |")
    md.append(f">")
    md.append(f"> {T('rpt_related', name=repo_name)}")
    md.append("\n---\n")

    md.append(f"## {T('rpt_overview')}\n")
    md.append(T("rpt_overview_desc", nodes=total_nodes, edges=total_edges, files=total_files))
    if node_data:
        top3 = ", ".join(f"{t} ({c:,})" for t, c in node_data[:3])
        md.append(T("rpt_node_top3", top3=top3))
    md.append("")
    node_bars = _bar_chart_text(node_data[:10])
    edge_bars = _bar_chart_text(edge_data[:8])
    md.append("```")
    md.append(f"    {T('rpt_node_dist')}")
    md.append(f"    ─────────────")
    md.append(node_bars)
    md.append(f"\n    {T('rpt_edge_dist')}")
    md.append(f"    ─────────────")
    md.append(edge_bars)
    md.append("```\n")

    # ── 模块饼图 + 表格 ──
    if module_dist:
        pie_items = "\n".join(f'    "{mod} ({cnt})" : {cnt}' for mod, cnt in module_dist[:12])
        md.append(f"## {T('rpt_module_dist')}\n")
        md.append("```mermaid")
        md.append(f"pie title {T('rpt_pie_title')}")
        md.append(pie_items)
        md.append("```\n")
        md.append(f"| {T('rpt_module')} | {T('rpt_file_count')} | {T('rpt_pct')} |")
        md.append("|------|--------|------|")
        for mod, cnt in module_dist:
            pct = cnt * 100 // total_files if total_files else 0
            md.append(f"| `{mod}` | {cnt} | {pct}% |")
        md.append("")

    # ── 跨模块依赖 ──
    if cross_deps:
        md.append(f"## {T('rpt_cross_deps')}\n")
        md.append(f"{T('rpt_cross_desc')}\n")
        # 构建模块级依赖 Mermaid
        mod_dep_counter: Counter = Counter()
        for r in cross_deps:
            if len(r) >= 3:
                src_mod = _module_prefix(r[0])
                dst_mod = _module_prefix(r[1])
                if src_mod != dst_mod:
                    mod_dep_counter[(src_mod, dst_mod)] += int(r[2])
        top_mod_deps = mod_dep_counter.most_common(12)
        if top_mod_deps:
            md.append("```mermaid")
            md.append("graph LR")
            seen_mods = set()
            for (src, dst), w in top_mod_deps:
                src_id = src.replace("/", "_").replace("(", "").replace(")", "")
                dst_id = dst.replace("/", "_").replace("(", "").replace(")", "")
                md.append(f"    {src_id}[\"{src}\"] -->|{w}| {dst_id}[\"{dst}\"]")
                seen_mods.add(src)
                seen_mods.add(dst)
            md.append("```\n")
        md.append(f"| {T('rpt_caller_file')} | {T('rpt_callee_file')} | {T('rpt_call_count')} |")
        md.append("|-----------|-----------|---------|")
        for r in cross_deps[:15]:
            if len(r) >= 3:
                md.append(f"| {r[0]} | {r[1]} | {r[2]} |")
        md.append("")

    # ── 文件间 IMPORTS ──
    if imports:
        # 汇总为模块级
        import_mod_counter: Counter = Counter()
        for r in imports:
            if len(r) >= 2:
                s, d = _module_prefix(r[0]), _module_prefix(r[1])
                if s != d:
                    import_mod_counter[(s, d)] += 1
        top_imports = import_mod_counter.most_common(10)
        if top_imports:
            md.append(f"## {T('rpt_imports')}\n")
            md.append("```mermaid")
            md.append("graph LR")
            for (s, d), w in top_imports:
                sid = s.replace("/", "_").replace("(", "").replace(")", "")
                did = d.replace("/", "_").replace("(", "").replace(")", "")
                md.append(f"    {sid}[\"{s}\"] -->|{w}| {did}[\"{d}\"]")
            md.append("```\n")

    # ── Hub 节点 ──
    hubs_all = []
    for r in hub_fns:
        if len(r) >= 3:
            hubs_all.append((r[0], r[1], r[2], "Function"))
    for r in hub_classes:
        if len(r) >= 3:
            hubs_all.append((r[0], r[1], r[2], "Class"))
    if hubs_all:
        hubs_all.sort(key=lambda x: -int(x[2]))
        md.append(f"## {T('rpt_hubs')}\n")
        md.append(f"{T('rpt_hubs_desc')}\n")
        md.append(f"| {T('rpt_symbol')} | {T('rpt_file')} | {T('rpt_refs')} | {T('rpt_type')} |")
        md.append("|------|------|---------|------|")
        for name, fpath, refs, label in hubs_all[:20]:
            md.append(f"| `{name}` | {fpath} | {refs} | {label} |")
        md.append("")

    # ── 顶级调用者 ──
    if top_callers:
        md.append(f"## {T('rpt_top_callers')}\n")
        md.append(f"{T('rpt_top_callers_desc')}\n")
        md.append(f"| {T('rpt_function')} | {T('rpt_file')} | {T('rpt_call_n')} |")
        md.append("|------|------|---------|")
        for r in top_callers:
            if len(r) >= 3:
                md.append(f"| `{r[0]}` | {r[1]} | {r[2]} |")
        md.append("")

    # ── 执行流程 (Process Flows) ──
    if proc_sorted:
        md.append(f"## {T('rpt_proc_flows')}\n")
        md.append(f"{T('rpt_proc_desc', n=n_processes, m=min(10, len(proc_sorted)))}\n")
        for pid, pg in proc_sorted[:10]:
            type_tag = f"`{pg['type']}`" if pg["type"] else ""
            md.append(f"### {pg['label']} {type_tag} {pg['stepCount']} steps")
            # 涉及文件列表 (去重, 保序)
            seen_files: list[str] = []
            for sname, sfile, _ in pg["steps"]:
                if sfile and sfile not in seen_files:
                    seen_files.append(sfile)
            if seen_files:
                md.append(f"> {' → '.join(seen_files)}")
            md.append("")
            for i, (sname, sfile, _) in enumerate(pg["steps"], 1):
                md.append(f"{i}. `{sname}` ({sfile})")
            md.append("")

    # ── 关键文件索引 ──
    if file_def_map:
        # 收集 hub 符号名集合，用于 ★ 标记
        hub_names_set = set()
        for r in hub_fns:
            if len(r) >= 3:
                hub_names_set.add(r[0])
        for r in hub_classes:
            if len(r) >= 3:
                hub_names_set.add(r[0])
        # 按符号数降序，只展示 >= 5 的文件
        file_def_sorted = sorted(file_def_map.items(), key=lambda x: -len(x[1]))
        file_def_sorted = [(f, syms) for f, syms in file_def_sorted if len(syms) >= 5][:15]
        if file_def_sorted:
            md.append(f"## {T('rpt_file_index')}\n")
            md.append(f"{T('rpt_file_index_desc')}\n")
            md.append(f"| {T('rpt_file_col')} | {T('rpt_sym_count')} | {T('rpt_main_defs')} |")
            md.append("|------|--------|---------|")
            for fpath, syms in file_def_sorted:
                preview_names = []
                for sym_name, _ in syms[:6]:
                    star = "★" if sym_name in hub_names_set else ""
                    preview_names.append(f"`{sym_name}`{star}")
                more = ", ..." if len(syms) > 6 else ""
                md.append(f"| {fpath} | {len(syms)} | {', '.join(preview_names)}{more} |")
            md.append("")

    # ── 类继承 ──
    if inheritance:
        parent_map: dict[str, list[str]] = {}
        for r in inheritance:
            if len(r) >= 2:
                parent_map.setdefault(r[1], []).append(r[0])
        sorted_parents = sorted(parent_map.items(), key=lambda x: -len(x[1]))[:20]
        total_edges_ih = sum(len(ch) for _, ch in sorted_parents)
        md.append(f"## {T('rpt_inherit')}\n")
        md.append(f"{T('rpt_inherit_desc', n=len(inheritance), m=len(parent_map))}\n")
        if total_edges_ih <= 40:
            md.append("```mermaid")
            md.append("classDiagram")
            for parent, children in sorted_parents:
                for child in children:
                    md.append(f"    {parent} <|-- {child}")
            md.append("```\n")
        else:
            md.append(f"| {T('rpt_parent')} | {T('rpt_child')} |")
            md.append("|------|------|")
            for parent, children in sorted_parents:
                md.append(f"| `{parent}` | {', '.join(f'`{c}`' for c in children)} |")
            md.append("")

    # ── 核心 Struct ──
    if structs:
        # 按模块分组，优先显示核心模块
        struct_by_mod: dict[str, list[str]] = {}
        for r in structs:
            if len(r) >= 2:
                mod = _module_prefix(r[1])
                struct_by_mod.setdefault(mod, []).append(r[0])
        md.append(f"## {T('rpt_structs')}\n")
        md.append(f"{T('rpt_structs_desc', n=len(structs))}\n")
        for mod in sorted(struct_by_mod, key=lambda m: -len(struct_by_mod[m])):
            names = struct_by_mod[mod]
            preview = ", ".join(f"`{n}`" for n in names[:8])
            more = f" ... (+{len(names)-8})" if len(names) > 8 else ""
            md.append(f"- **{mod}/** ({len(names)}): {preview}{more}")
        md.append("")

    # ── Enum 列表 ──
    if enums:
        md.append(f"## {T('rpt_enums')}\n")
        enum_by_mod: dict[str, list[str]] = {}
        for r in enums:
            if len(r) >= 2:
                mod = _module_prefix(r[1])
                enum_by_mod.setdefault(mod, []).append(r[0])
        for mod in sorted(enum_by_mod, key=lambda m: -len(enum_by_mod[m])):
            names = enum_by_mod[mod]
            preview = ", ".join(f"`{n}`" for n in names[:8])
            more = f" ... (+{len(names)-8})" if len(names) > 8 else ""
            md.append(f"- **{mod}/** ({len(names)}): {preview}{more}")
        md.append("")

    # ── 命名空间 ──
    if namespaces:
        md.append(f"## {T('rpt_namespaces')}\n")
        md.append("```")
        for i, ns in enumerate(namespaces):
            prefix = "└──" if i == len(namespaces) - 1 else "├──"
            md.append(f"{prefix} {ns}::")
        md.append("```\n")

    # ── 社区 (增强版: 大社区展示成员详情) ──
    if communities:
        md.append(f"## {T('rpt_community_struct')}\n")
        md.append(f"{T('rpt_community_desc', n=total_communities)}\n")
        # 大社区 (symbolCount >= 10): 展示文件列表 + 符号列表
        for c in communities:
            if len(c) >= 4:
                cid = c[0]
                try:
                    sym_count = int(c[2])
                except (ValueError, TypeError):
                    sym_count = 0
                try:
                    coh = f"{float(c[3]):.2f}"
                except (ValueError, TypeError):
                    coh = c[3]
                detail = comm_detail.get(cid)
                if sym_count >= 10 and detail and detail["members"]:
                    md.append(f"### {cid} — {c[1]} ({sym_count} symbols, cohesion {coh})\n")
                    # 涉及文件 (去重, 最多 8 个)
                    seen: list[str] = []
                    for _, _, fp in detail["members"]:
                        if fp and fp not in seen:
                            seen.append(fp)
                    file_preview = ", ".join(seen[:8])
                    if len(seen) > 8:
                        file_preview += ", ..."
                    md.append(f"**{T('rpt_involved_files')}**: {file_preview}")
                    sym_preview = ", ".join(f"`{n}`" for n, _, _ in detail["members"][:8])
                    if len(detail["members"]) > 8:
                        sym_preview += ", ..."
                    md.append(f"**{T('rpt_core_symbols')}**: {sym_preview}\n")
        # 总结表格 (所有社区)
        md.append(f"### {T('rpt_comm_overview')}\n")
        md.append(f"| {T('rpt_comm_col')} | {T('rpt_domain')} | {T('rpt_sym_n')} | {T('rpt_cohesion')} |")
        md.append("|------|-----|--------|--------|")
        for c in communities:
            if len(c) >= 4:
                try:
                    coh = f"{float(c[3]):.2f}"
                except (ValueError, TypeError):
                    coh = c[3]
                md.append(f"| {c[0]} | {c[1]} | {c[2]} | {coh} |")
        md.append("")

    # ── 边统计 ──
    if edge_data:
        md.append(f"## {T('rpt_edge_stats')}\n")
        md.append(f"| {T('rpt_edge_type')} | {T('rpt_meaning')} | {T('rpt_count')} | {T('rpt_pct')} |")
        md.append("|--------|------|------|------|")
        edge_desc = {
            "CALLS": T("rpt_edge_calls"), "DEFINES": T("rpt_edge_defines"),
            "IMPORTS": T("rpt_edge_imports"), "CONTAINS": T("rpt_edge_contains"),
            "MEMBER_OF": T("rpt_edge_member"), "STEP_IN_PROCESS": T("rpt_edge_step"),
            "EXTENDS": T("rpt_edge_extends"),
        }
        for label, val in edge_data:
            pct = val * 100 // total_edges if total_edges else 0
            desc = edge_desc.get(label, "")
            md.append(f"| `{label}` | {desc} | {val:,} | {pct}% |")
        md.append(f"| **Total** | | **{total_edges:,}** | |")
        md.append("")
        md.append("```")
        for label, val in edge_data:
            bar = "█" * (val * 20 // (edge_data[0][1] or 1))
            md.append(f"{label:<20} {val:>6,}  {bar}")
        md.append("```\n")

    # 写入文件
    vault_dir = OBSIDIAN_VAULT / "Projects" / repo_name
    vault_dir.mkdir(parents=True, exist_ok=True)
    doc_path = vault_dir / f"{repo_name} {T('rpt_code_graph_doc')}.md"
    doc_path.write_text("\n".join(md), encoding="utf-8")

    # 交叉引用
    main_doc = vault_dir / f"{repo_name}.md"
    link_text = f"[[{repo_name} {T('rpt_code_graph_doc')}]]"
    if main_doc.is_file():
        content = main_doc.read_text(encoding="utf-8")
        if link_text not in content:
            # 找 [!tip] 详细文档 段落末尾追加
            if "> [!tip]" in content:
                lines = content.split("\n")
                insert_idx = -1
                in_tip = False
                for i, line in enumerate(lines):
                    if "[!tip]" in line:
                        in_tip = True
                    elif in_tip and not line.startswith(">"):
                        insert_idx = i
                        break
                if insert_idx > 0:
                    lines.insert(insert_idx, f"> - {link_text} — {T('rpt_xref_label')}")
                    main_doc.write_text("\n".join(lines), encoding="utf-8")
                    console.print(f"  [dim]{T('xref_added', name=repo_name)}[/dim]")

    console.print(f"\n[green]{T('graph_ok', path=str(doc_path))}[/green]")
    console.print(f"  [dim]{T('graph_stats', nodes=total_nodes, edges=total_edges, communities=total_communities, processes=n_processes)}[/dim]")


def cmd_graph(args):
    """GitNexus 代码图谱分析 (调度器)"""
    graph_cmd = getattr(args, "graph_cmd", "overview") or "overview"
    dispatch = {
        "index": cmd_graph_index,
        "overview": cmd_graph_overview,
        "query": cmd_graph_query,
        "deps": cmd_graph_deps,
        "community": cmd_graph_community,
        "report": cmd_graph_report,
        "hierarchy": cmd_graph_hierarchy,
        "hubs": cmd_graph_hubs,
        "modules": cmd_graph_modules,
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
        console.print(f"[red]{T('cannot_scan', name=repo_name)}[/red]")
        return

    console.print(f"[bold]{T('gen_doc', name=repo_name)}[/bold]\n")

    # ── 收集详细信息 ──
    branches = run_git(repo_path, "branch", "--list").split("\n")
    branches = [b.strip().lstrip("* ") for b in branches if b.strip()]
    tags = run_git(repo_path, "tag", "--list").split("\n")
    tags = [t for t in tags if t.strip()]
    latest_tag = tags[-1] if tags else T("doc_none")

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
            console.print(f"  [dim]{T('copying', path=str(src.relative_to(repo_path)))}[/dim]")

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
    status_text = T("doc_clean") if info["dirty"] == 0 else T("doc_dirty", n=info["dirty"])
    commits_line = T("doc_commits_week_month", commits=info["commits"], week=week_n, month=month_n)
    md_parts.append(f"""> [!info] {T('doc_info')}
> | {T('doc_attr')} | {T('doc_value')} |
> |------|------|
> | {T('doc_path')} | `{path_display}` |
> | {T('doc_remote')} | `{info.get('remote_url', T('doc_none'))}` |
> | {T('doc_branch')} | `{info['branch']}`{branch_extra} |
> | {T('doc_language')} | {lang_str} |
> | {T('lbl_commits')} | {commits_line} |
> | {T('doc_contribs')} | {len(contributors)} ({contribs}) |
> | {T('doc_tags')} | {len(tags)} tags (latest: {latest_tag}) |
> | {T('doc_status')} | {status_emoji} {status_text} |
""")

    # 项目概述 (用 Obsidian callout)
    if overview:
        # 将概述包装为 callout
        callout_lines = overview.split("\n")
        callout = f"> [!abstract] {T('doc_overview')}\n" + "\n".join(f"> {l}" for l in callout_lines)
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
            trimmed.append(f"\n> *{T('doc_arch_full', n=len(arch_lines))}*")
            architecture = "\n".join(trimmed)
        md_parts.append(f"## {T('doc_arch')}\n\n{architecture}\n")

    # 关键图表（使用 Obsidian wikilink 嵌入）
    if copied_imgs:
        md_parts.append(f"## {T('doc_diagrams')}\n")
        for img in copied_imgs:
            label = img.replace(".png", "").replace("_", " ")
            md_parts.append(f"### {label}\n\n![[{img}]]\n")

    # 目录结构
    if tree_out:
        md_parts.append(f"## {T('doc_source_tree')}\n\n```\n{tree_out}\n```\n")

    # 文档索引 (callout)
    if docs_index:
        lines = [f"> [!folder]- {T('doc_docs_index')}"] + [f"> {item}" for item in docs_index]
        md_parts.append("\n".join(lines) + "\n")

    # 最近活动 (callout, 可折叠)
    if recent_commits:
        lines = [f"> [!timeline]- {T('doc_recent')}"]
        for rel, msg in recent_commits:
            # 按类型着色提示
            prefix = "🟢" if msg.startswith("feat") else "🟡" if msg.startswith("fix") else "⚪"
            lines.append(f"> {prefix} **{rel}** — {msg}")
        md_parts.append("\n".join(lines) + "\n")

    # 写入
    doc_path = vault_dir / f"{repo_name}.md"
    doc_path.write_text("\n".join(md_parts), encoding="utf-8")

    console.print(f"\n[green]{T('doc_ok', path=str(doc_path))}[/green]")
    console.print(f"  [dim]{T('doc_stats', imgs=len(copied_imgs), commits=len(recent_commits))}[/dim]")


GLOBAL_FLAGS = {"--path", "--sort", "--filter", "--json", "--watch", "--lang", "--no-color"}
GLOBAL_FLAGS_WITH_VALUE = {"--path", "--sort", "--filter", "--watch", "--lang"}


def preprocess_argv(argv: list[str]) -> list[str]:
    """将全局选项移到子命令之前，允许 `cb health --filter foo` 的用法"""
    subcommands = {
        "dashboard", "activity", "health", "detail", "stats",
        "open", "dirty", "each", "pull", "push", "commit", "stash", "grep",
        "doc", "graph", "config", "completions",
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


def cmd_completions(args):
    """Generate shell completion script."""
    shell = getattr(args, "shell", "bash")
    _SUBCOMMANDS = "dashboard activity health detail stats open dirty each pull push commit stash grep doc graph config"
    _GLOBAL_OPTS = "--path --sort --filter --json --watch --lang --no-color --version"
    _SORT_OPTS = "name activity commits changes"
    _LANG_OPTS = "auto en zh"
    _GRAPH_ACTIONS = "index overview query deps community report hierarchy hubs modules"
    _PANELS = "status branch log stash"
    _STASH_ACTIONS = "push pop list"
    if shell == "bash":
        print(f"""\
_cb_completions() {{
    local cur prev subcmd
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    # find subcommand
    subcmd=""
    for word in "${{COMP_WORDS[@]:1}}"; do
        case "$word" in
            dashboard|activity|health|detail|stats|open|dirty|each|pull|push|commit|stash|grep|doc|graph|config)
                subcmd="$word"; break ;;
        esac
    done
    case "$prev" in
        --sort) COMPREPLY=($(compgen -W "{_SORT_OPTS}" -- "$cur")); return ;;
        --lang) COMPREPLY=($(compgen -W "{_LANG_OPTS}" -- "$cur")); return ;;
        --path) COMPREPLY=($(compgen -d -- "$cur")); return ;;
    esac
    if [[ -z "$subcmd" ]]; then
        COMPREPLY=($(compgen -W "{_SUBCOMMANDS} {_GLOBAL_OPTS}" -- "$cur"))
        return
    fi
    case "$subcmd" in
        graph) COMPREPLY=($(compgen -W "{_GRAPH_ACTIONS}" -- "$cur")) ;;
        open)  COMPREPLY=($(compgen -W "{_PANELS}" -- "$cur")) ;;
        stash) COMPREPLY=($(compgen -W "{_STASH_ACTIONS}" -- "$cur")) ;;
        *)     COMPREPLY=($(compgen -W "{_GLOBAL_OPTS}" -- "$cur")) ;;
    esac
}}
complete -F _cb_completions cb codeboard""")
    elif shell == "zsh":
        print(f"""\
#compdef cb codeboard
_cb() {{
    local -a subcmds=({_SUBCOMMANDS})
    local -a global_opts=({_GLOBAL_OPTS})
    local -a graph_actions=({_GRAPH_ACTIONS})
    local -a panels=({_PANELS})
    local -a stash_actions=({_STASH_ACTIONS})
    local subcmd=""
    for word in "${{words[@]:1}}"; do
        if (( $subcmds[(Ie)$word] )); then
            subcmd="$word"; break
        fi
    done
    if [[ -z "$subcmd" ]]; then
        _describe 'command' subcmds
        _describe 'option' global_opts
        return
    fi
    case "$subcmd" in
        graph) _describe 'action' graph_actions ;;
        open)  _describe 'panel' panels ;;
        stash) _describe 'action' stash_actions ;;
        detail|commit|doc) _files -/ ;;
        *)     _describe 'option' global_opts ;;
    esac
}}
_cb""")
    elif shell == "fish":
        print(f"""\
# Fish completions for cb/codeboard
set -l subcmds {_SUBCOMMANDS}
set -l graph_actions {_GRAPH_ACTIONS}
complete -c cb -c codeboard -f
complete -c cb -c codeboard -n "not __fish_seen_subcommand_from $subcmds" -a "$subcmds"
complete -c cb -c codeboard -l path -r -F
complete -c cb -c codeboard -l sort -r -a "{_SORT_OPTS}"
complete -c cb -c codeboard -l filter -r
complete -c cb -c codeboard -l json
complete -c cb -c codeboard -l watch -r
complete -c cb -c codeboard -l lang -r -a "{_LANG_OPTS}"
complete -c cb -c codeboard -l no-color
complete -c cb -c codeboard -l version
complete -c cb -c codeboard -n "__fish_seen_subcommand_from graph" -a "$graph_actions"
complete -c cb -c codeboard -n "__fish_seen_subcommand_from open" -a "{_PANELS}"
complete -c cb -c codeboard -n "__fish_seen_subcommand_from stash" -a "{_STASH_ACTIONS}"
""")


def cmd_config(args):
    """Show or generate config file."""
    if CONFIG_FILE.is_file():
        console.print(f"[bold]Config:[/bold] {CONFIG_FILE}")
        console.print(CONFIG_FILE.read_text())
    else:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(_generate_default_config())
        console.print(f"[green]Generated default config: {CONFIG_FILE}[/green]")


def main():
    global _ui_lang, console

    sys.argv[1:] = preprocess_argv(sys.argv[1:])

    parser = argparse.ArgumentParser(
        prog="codeboard",
        description="CodeBoard — Git repository dashboard for your local codebase",
    )
    parser.add_argument("-V", "--version", action="version", version=f"codeboard {__version__}")
    parser.add_argument("--path", default=str(DEFAULT_CODE_DIR), help="Scan directory (default: ~/Code)")
    parser.add_argument("--sort", choices=["name", "activity", "commits", "changes"], default="activity", help="Sort order")
    parser.add_argument("--filter", default="", help="Filter repos by name")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--watch", type=int, metavar="N", default=0, help="Auto-refresh every N seconds")
    parser.add_argument("--lang", choices=["auto", "en", "zh"], default=None, help="UI language (default: auto)")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("dashboard", help="Main dashboard (default)")
    sub.add_parser("activity", help="Cross-repo commit timeline").add_argument("--limit", type=int, default=30, help="Number of entries")
    sub.add_parser("health", help="Health check report")

    detail_parser = sub.add_parser("detail", help="Single repo details")
    detail_parser.add_argument("repo", help="Repository name")

    sub.add_parser("stats", help="Summary statistics")

    open_parser = sub.add_parser("open", help="Open repo in lazygit")
    open_parser.add_argument("repo", help="Repository name")
    open_parser.add_argument("panel", nargs="?", choices=["status", "branch", "log", "stash"], help="lazygit focus panel")

    sub.add_parser("dirty", help="List dirty repos, open with lazygit")
    sub.add_parser("each", help="Process dirty repos one by one with lazygit")

    sub.add_parser("pull", help="Pull all repos with remote")
    sub.add_parser("push", help="Push all repos with ahead commits")

    commit_parser = sub.add_parser("commit", help="Quick commit a repo")
    commit_parser.add_argument("repo", help="Repository name")
    commit_parser.add_argument("-m", "--message", required=True, help="Commit message")
    commit_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    stash_parser = sub.add_parser("stash", help="Quick stash a repo")
    stash_parser.add_argument("repo", help="Repository name")
    stash_parser.add_argument("action", nargs="?", choices=["push", "pop", "list"], default="push", help="Stash action (default: push)")
    stash_parser.add_argument("-m", "--message", help="Stash message")

    grep_parser = sub.add_parser("grep", help="Search code across repos")
    grep_parser.add_argument("pattern", help="Search pattern (regex)")

    doc_parser = sub.add_parser("doc", help="Generate Obsidian project doc")
    doc_parser.add_argument("repo", help="Repository name")

    graph_parser = sub.add_parser("graph", help="GitNexus code graph analysis")
    graph_parser.add_argument("repo", help="Repository name")
    graph_parser.add_argument("graph_cmd", nargs="?", default="overview",
                              choices=["index", "query", "deps", "community", "overview",
                                       "report", "hierarchy", "hubs", "modules"],
                              help="Action: index|overview|query|deps|community|report|hierarchy|hubs|modules")
    graph_parser.add_argument("keywords", nargs="?", default="", help="Search keywords for query")

    sub.add_parser("config", help="Show or generate config file")

    comp_parser = sub.add_parser("completions", help="Generate shell completion script")
    comp_parser.add_argument("shell", nargs="?", default="bash", choices=["bash", "zsh", "fish"], help="Shell type (default: bash)")

    args = parser.parse_args()

    # Apply --lang and --no-color
    if args.lang:
        _ui_lang = args.lang
    if args.no_color:
        console = Console(no_color=True, highlight=False)

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
        "config": cmd_config,
        "completions": cmd_completions,
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
            console.print(f"\n[dim]{T('watch_ft', n=args.watch, t=elapsed)}[/dim]")
            time.sleep(args.watch)
    else:
        handler(args)


if __name__ == "__main__":
    main()
