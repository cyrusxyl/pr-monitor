# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- Always use `uv run` to execute Python commands (e.g., `uv run python -c ...`)
- `uv sync` — install/update dependencies
- `uv run pr-monitor` — run the application

No linting, formatting, or test suite is configured.

## Architecture

This is a single-file Textual TUI app (`pr_monitor/app.py`) that monitors GitHub PRs across multiple accounts and GitHub Enterprise instances.

### Key classes

- **`Priority` (IntEnum)** — HIGH=1, MEDIUM=2, LOW=3; drives row sort order
- **`PRDashboard` (Textual `App`)** — the entire application; all logic lives here

### Data flow in `refresh_data()`

Two-phase load to show PRs before checks finish:

1. **Phase 1** — `asyncio.gather` all accounts → within each account, `asyncio.gather` all search queries → process results into `row_data` dicts → sort by initial priority → build `DataTable` sections and mount immediately (checks show `⚪`)
2. **Phase 2** — `asyncio.gather` all `get_check_status()` calls → call `table.update_cell()` for each result as it lands → re-evaluate priority (failing checks on own PR elevates to HIGH) → patch status cells that changed

### Key methods

| Method | Purpose |
|---|---|
| `load_config()` | Reads `~/.config/pr-monitor/config.yaml` (XDG-aware) |
| `build_queries()` | Converts account config into `(label, query_string)` pairs |
| `fetch_prs(account)` | Hits `/search/issues` for all queries concurrently |
| `get_check_status(pr, headers, client)` | Hits Check Runs API then falls back to Commit Status API; also collects reviewer info |
| `determine_pr_status(pr, query_label, username, reviewer_info)` | Pure logic — returns `(Priority, status_string)` |
| `get_authenticated_user()` | Cached by `token_env_var`; hits `/user` once per token |

### Config schema (`~/.config/pr-monitor/config.yaml`)

```yaml
general:
  refresh_interval_seconds: 300
accounts:
  - id: "personal"
    label: "Display Name"
    api_base: "https://api.github.com"   # override for GHE
    token_env_var: "GH_TOKEN"            # PAT stored in env, not config
    filters:
      scope: "all"          # or "specific" (requires repos[])
      repos: []
      queries:
        - label: "Review Requested"
          query: "is:pr is:open review-requested:@me"
```

Authentication is always via env vars; the config file never holds tokens.

### UI structure

One `DataTable` per query label, each inside a `Vertical` section mounted into `#main-container`. Row keys are `"{account_label}_{pr_id}"`. `self.pr_urls` maps row keys to PR URLs for `action_open_pr`.
