# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-03-06

### Added

- **Dashboard** — Overview of all repos: branch, last commit, dirty status, language, remote
- **Activity** — Cross-repo commit timeline with `--limit`
- **Health** — Find uncommitted changes, unpushed commits, repos behind remote, inactive repos
- **Detail** — Deep dive into a single repo: contributors, languages, recent commits, activity chart
- **Stats** — Aggregate statistics: language distribution, weekly top, remote distribution
- **Grep** — Search code across all repos (regex)
- **Batch operations** — `pull`, `push`, `commit`, `stash` across repos
- **lazygit integration** — `open`, `dirty`, `each` commands
- **Doc** — Generate Obsidian project documentation
- **Graph** — Code graph analysis via GitNexus (overview, index, query, deps, community, report, hierarchy, hubs, modules)
- **Configuration** — TOML config at `~/.config/codeboard/config.toml`
- **i18n** — Full English and Chinese UI support (166 keys), auto-detect or `--lang`
- **Global options** — `--path`, `--sort`, `--filter`, `--json`, `--watch`, `--lang`, `--no-color`, `--version`
- **Packaging** — pip-installable with `cb` and `codeboard` console scripts
