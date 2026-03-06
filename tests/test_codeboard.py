"""Tests for codeboard — pure function unit tests (no git/external deps)."""

import json
from datetime import datetime, timezone, timedelta

import codeboard


# ── T() i18n ──────────────────────────────────────────────────────────────────

class TestI18n:
    def test_t_en(self):
        codeboard._ui_lang = "en"
        assert codeboard.T("col_name") == "Name"
        assert codeboard.T("secs_ago", n=5) == "5s ago"

    def test_t_zh(self):
        codeboard._ui_lang = "zh"
        assert codeboard.T("col_name") == "名称"
        assert codeboard.T("secs_ago", n=5) == "5秒前"

    def test_t_auto_falls_back(self):
        codeboard._ui_lang = "auto"
        result = codeboard.T("col_name")
        assert result in ("Name", "名称")

    def test_t_missing_key(self):
        codeboard._ui_lang = "en"
        result = codeboard.T("nonexistent_key_xyz")
        assert result == "nonexistent_key_xyz"

    def test_all_keys_match(self):
        """Every key in en must exist in zh and vice versa."""
        en_keys = set(codeboard._I18N["en"])
        zh_keys = set(codeboard._I18N["zh"])
        assert en_keys == zh_keys, f"Mismatch: en-only={en_keys - zh_keys}, zh-only={zh_keys - en_keys}"


# ── relative_time ─────────────────────────────────────────────────────────────

class TestRelativeTime:
    def setup_method(self):
        codeboard._ui_lang = "en"

    def test_just_now(self):
        now = datetime.now(timezone.utc)
        assert codeboard.relative_time(now) == "0s ago"

    def test_minutes(self):
        dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert codeboard.relative_time(dt) == "5m ago"

    def test_hours(self):
        dt = datetime.now(timezone.utc) - timedelta(hours=3)
        assert codeboard.relative_time(dt) == "3h ago"

    def test_days(self):
        dt = datetime.now(timezone.utc) - timedelta(days=7)
        assert codeboard.relative_time(dt) == "7d ago"

    def test_months(self):
        dt = datetime.now(timezone.utc) - timedelta(days=60)
        assert codeboard.relative_time(dt) == "2mo ago"

    def test_years(self):
        dt = datetime.now(timezone.utc) - timedelta(days=400)
        assert codeboard.relative_time(dt) == "1y ago"

    def test_naive_datetime(self):
        """Naive datetime is treated as UTC by relative_time."""
        dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        result = codeboard.relative_time(dt)
        assert "h ago" in result


# ── detect_remote_type ────────────────────────────────────────────────────────

class TestDetectRemoteType:
    def test_github_ssh(self):
        assert codeboard.detect_remote_type("git@github.com:user/repo.git") == "github"

    def test_github_https(self):
        assert codeboard.detect_remote_type("https://github.com/user/repo") == "github"

    def test_gitlab(self):
        assert codeboard.detect_remote_type("git@gitlab.example.com:group/proj.git") == "gitlab"

    def test_gitee(self):
        assert codeboard.detect_remote_type("https://gitee.com/user/repo") == "gitee"

    def test_bitbucket(self):
        assert codeboard.detect_remote_type("git@bitbucket.org:user/repo.git") == "bitbucket"

    def test_other(self):
        assert codeboard.detect_remote_type("https://my-server.com/repo.git") == "other"

    def test_empty(self):
        assert codeboard.detect_remote_type("") == "none"


# ── _module_prefix ────────────────────────────────────────────────────────────

class TestModulePrefix:
    def test_nested_path(self):
        assert codeboard._module_prefix("src/core/main.cpp") == "src"

    def test_root_file(self):
        assert codeboard._module_prefix("main.py") == "(root)"

    def test_empty(self):
        assert codeboard._module_prefix("") == "(root)"

    def test_windows_path(self):
        assert codeboard._module_prefix("include\\foo\\bar.h") == "include"


# ── _parse_md_table ───────────────────────────────────────────────────────────

class TestParseMdTable:
    def test_basic(self):
        data = json.dumps({"markdown": "| type | count |\n|---|---|\n| Function | 100 |\n| Class | 50 |"})
        rows = codeboard._parse_md_table(data)
        assert len(rows) == 2
        assert rows[0] == ["Function", "100"]
        assert rows[1] == ["Class", "50"]

    def test_empty_json(self):
        assert codeboard._parse_md_table("") == []

    def test_invalid_json(self):
        assert codeboard._parse_md_table("not json") == []

    def test_no_markdown_key(self):
        assert codeboard._parse_md_table(json.dumps({"other": "data"})) == []

    def test_no_data_rows(self):
        data = json.dumps({"markdown": "| h1 | h2 |\n|---|---|"})
        assert codeboard._parse_md_table(data) == []


# ── _bar_chart_text ───────────────────────────────────────────────────────────

class TestBarChartText:
    def test_basic(self):
        items = [("Function", 100), ("Class", 50)]
        result = codeboard._bar_chart_text(items)
        assert "Function" in result
        assert "Class" in result
        assert "100" in result

    def test_empty(self):
        assert codeboard._bar_chart_text([]) == ""

    def test_single_item(self):
        result = codeboard._bar_chart_text([("X", 1)])
        assert "X" in result
        assert "█" in result


# ── sort_repos ────────────────────────────────────────────────────────────────

class TestSortRepos:
    def _make_repos(self):
        return [
            {"name": "bravo", "commits": 10, "dirty": 5, "last_time_ts": 100},
            {"name": "alpha", "commits": 30, "dirty": 0, "last_time_ts": 300},
            {"name": "charlie", "commits": 20, "dirty": 3, "last_time_ts": 200},
        ]

    def test_sort_name(self):
        repos = self._make_repos()
        result = codeboard.sort_repos(repos, "name")
        assert [r["name"] for r in result] == ["alpha", "bravo", "charlie"]

    def test_sort_commits(self):
        repos = self._make_repos()
        result = codeboard.sort_repos(repos, "commits")
        assert result[0]["name"] == "alpha"

    def test_sort_changes(self):
        repos = self._make_repos()
        result = codeboard.sort_repos(repos, "changes")
        assert result[0]["name"] == "bravo"

    def test_sort_activity(self):
        repos = self._make_repos()
        result = codeboard.sort_repos(repos, "activity")
        assert result[0]["name"] == "alpha"


# ── preprocess_argv ───────────────────────────────────────────────────────────

class TestPreprocessArgv:
    def test_no_subcommand(self):
        argv = ["--filter", "foo"]
        assert codeboard.preprocess_argv(argv) == ["--filter", "foo"]

    def test_global_after_subcmd(self):
        argv = ["health", "--filter", "simona"]
        result = codeboard.preprocess_argv(argv)
        assert result == ["--filter", "simona", "health"]

    def test_flag_without_value(self):
        argv = ["health", "--json"]
        result = codeboard.preprocess_argv(argv)
        assert result == ["--json", "health"]

    def test_mixed(self):
        argv = ["--sort", "name", "health", "--filter", "foo", "--json"]
        result = codeboard.preprocess_argv(argv)
        assert "--filter" in result
        assert result.index("--filter") < result.index("health")
        assert "--json" in result

    def test_subcmd_with_args(self):
        argv = ["detail", "myrepo", "--json"]
        result = codeboard.preprocess_argv(argv)
        assert "myrepo" in result
        assert "--json" in result


# ── config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_config_content(self):
        content = codeboard._generate_default_config()
        assert "scan_dir" in content
        assert "lang" in content
        assert "extra_repos" in content

    def test_load_config_returns_dict(self):
        cfg = codeboard._load_config()
        assert isinstance(cfg, dict)
        assert "scan_dir" in cfg
