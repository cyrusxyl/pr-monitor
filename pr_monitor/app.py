#!/usr/bin/env python3
"""
Unified GitHub PR Dashboard
A TUI application for monitoring pull requests across multiple GitHub accounts.
"""

import os
import webbrowser
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

import httpx
import yaml
from dateutil.parser import parse as parse_date
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import DataTable, Footer, Header, Static
from textual.binding import Binding


class Priority(IntEnum):
    """PR priority levels (lower number = higher priority)."""
    HIGH = 1      # Needs your immediate attention (review requested, assigned)
    MEDIUM = 2    # Needs action (changes requested on your PR)
    LOW = 3       # Waiting (your PRs waiting for review, approved PRs)


class PRDashboard(App):
    """A Textual app for monitoring GitHub Pull Requests."""

    TITLE = "GitHub PR Monitor"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 1fr;
        overflow-y: auto;
    }

    .query-section {
        margin: 1 0;
        border: solid $primary;
        padding: 0 1;
    }

    .query-title {
        color: $accent;
        text-style: bold;
        padding: 1 0;
    }

    DataTable {
        height: auto;
        min-height: 3;
        border: none;
    }

    .title {
        text-align: center;
        color: $primary;
        text-style: bold;
        margin: 1;
    }

    .status-bar {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }

    .error-message {
        color: $error;
        text-align: center;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        ("enter", "open_pr", "Open PR"),
    ]

    def __init__(self):
        super().__init__()
        self.config = None
        self.pr_urls = {}  # Maps row keys to PR URLs
        self.last_update = None
        self.usernames = {}  # Cache: token_env_var -> username
        self.query_labels = []  # Track unique query labels for section organization

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Static("🔍 Unified PR Inbox", classes="title")
        yield Static("", id="status-bar", classes="status-bar")
        yield Container(id="main-container")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the application on mount."""
        # Load config and initial data
        self.load_config()

        # Trigger initial data fetch
        self.run_worker(self.refresh_data())

        # Set up auto-refresh timer (default: 5 minutes = 300 seconds)
        refresh_interval = 300
        if self.config and "general" in self.config:
            refresh_interval = self.config["general"].get("refresh_interval_seconds", 300)

        self.set_interval(refresh_interval, self.refresh_data)

    def load_config(self) -> None:
        """Load configuration from config.yaml."""
        config_path = Path("config.yaml")

        if not config_path.exists():
            self.show_error("config.yaml not found! Please create it from config.yaml.example")
            self.config = {"accounts": []}
            return

        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            self.show_error(f"Error loading config.yaml: {e}")
            self.config = {"accounts": []}

    def show_error(self, message: str) -> None:
        """Display an error message."""
        self.notify(message, severity="error", timeout=10)

    def build_queries(self, account_config: dict) -> list[tuple[str, str]]:
        """
        Construct GitHub Search API queries based on account configuration.

        Args:
            account_config: Account configuration dictionary

        Returns:
            List of tuples: [(query_label, query_string), ...]
        """
        queries = []

        # Get filter configuration
        filters = account_config.get("filters", {})
        scope = filters.get("scope", "all")

        # Get custom queries or use default
        query_configs = filters.get("queries", [
            {
                "label": "Review Requested",
                "query": "is:pr is:open review-requested:@me"
            }
        ])

        # Build each query
        for query_config in query_configs:
            label = query_config.get("label", "PRs")
            base_query = query_config.get("query", "is:pr is:open")

            # Parse the query into parts
            parts = base_query.split()

            # Add repository filters if scope is "specific"
            if scope == "specific":
                repos = filters.get("repos", [])
                if repos:
                    for repo in repos:
                        parts.append(f"repo:{repo}")

            queries.append((label, " ".join(parts)))

        return queries

    async def get_authenticated_user(self, api_base: str, token: str, token_env_var: str) -> str:
        """
        Get the authenticated user's username.

        Args:
            api_base: API base URL
            token: GitHub token
            token_env_var: Token environment variable name (used for caching)

        Returns:
            Username string, or empty string if not found
        """
        # Check cache first
        if token_env_var in self.usernames:
            return self.usernames[token_env_var]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                }
                response = await client.get(f"{api_base}/user", headers=headers)

                if response.status_code == 200:
                    username = response.json().get("login", "")
                    self.usernames[token_env_var] = username
                    return username
        except Exception:
            pass

        return ""

    async def get_check_status(
        self,
        pr: dict[str, Any],
        headers: dict[str, str],
        client: httpx.AsyncClient
    ) -> tuple[str, dict[str, Any]]:
        """
        Get the combined check status for a PR and reviewer information.

        Args:
            pr: PR data from GitHub Search API (simplified object)
            headers: HTTP headers with auth
            client: HTTP client to use

        Returns:
            Tuple of (status_emoji, reviewer_info_dict)
            reviewer_info_dict contains:
                - requested_reviewers: list of individual reviewer logins
                - requested_teams: list of team slugs
        """
        reviewer_info = {
            "requested_reviewers": [],
            "requested_teams": []
        }

        try:
            # Search API returns simplified objects - need to fetch full PR details
            # to get the commit SHA for checking status
            pull_request_url = pr.get("pull_request", {}).get("url")
            if not pull_request_url:
                return "⚪", reviewer_info  # Not a PR or URL not available

            # Fetch the full PR object
            response = await client.get(pull_request_url, headers=headers)
            if response.status_code != 200:
                return "⚪", reviewer_info

            full_pr = response.json()

            # Extract reviewer information
            reviewer_info["requested_reviewers"] = [
                reviewer.get("login") for reviewer in full_pr.get("requested_reviewers", [])
            ]
            reviewer_info["requested_teams"] = [
                team.get("slug") for team in full_pr.get("requested_teams", [])
            ]

            # Get the head commit SHA
            sha = full_pr.get("head", {}).get("sha")
            if not sha:
                return "⚪", reviewer_info

            # Get repository info
            repo_url = pr.get("repository_url")
            if not repo_url:
                return "⚪", reviewer_info

            # Use the Check Runs API (newer, more reliable)
            check_runs_url = f"{repo_url}/commits/{sha}/check-runs"
            response = await client.get(
                check_runs_url,
                headers={**headers, "Accept": "application/vnd.github.v3+json"}
            )

            if response.status_code == 200:
                check_data = response.json()
                check_runs = check_data.get("check_runs", [])

                if not check_runs:
                    # No check runs, try the older commit status API
                    status_url = f"{repo_url}/commits/{sha}/status"
                    response = await client.get(status_url, headers=headers)

                    if response.status_code == 200:
                        status_data = response.json()
                        state = status_data.get("state", "").lower()

                        # Map commit status states to emoji
                        status_map = {
                            "success": "✅",
                            "pending": "🟡",
                            "failure": "❌",
                            "error": "❌",
                        }
                        return status_map.get(state, "⚪"), reviewer_info

                    return "⚪", reviewer_info  # No checks at all

                # Process check runs
                conclusions = [run.get("conclusion") for run in check_runs]
                statuses = [run.get("status") for run in check_runs]

                # If any are in progress or queued
                if "in_progress" in statuses or "queued" in statuses:
                    return "🟡", reviewer_info

                # If any failed
                if "failure" in conclusions or "timed_out" in conclusions or "action_required" in conclusions:
                    return "❌", reviewer_info

                # If all succeeded
                if all(c == "success" for c in conclusions if c):
                    return "✅", reviewer_info

                # Neutral or skipped
                return "⚪", reviewer_info

        except Exception:
            pass

        return "⚪", reviewer_info  # Default: no status or error

    async def fetch_prs(self, account: dict) -> list[tuple[str, str, str, list[dict[str, Any]]]]:
        """
        Fetch PRs for a single account across all configured queries.

        Args:
            account: Account configuration dictionary

        Returns:
            List of tuples: [(account_label, username, query_label, list_of_prs), ...]
        """
        account_label = account.get("label", account.get("id", "Unknown"))
        results = []

        # Get token from environment variable
        token_env_var = account.get("token_env_var")
        if not token_env_var:
            self.notify(f"No token_env_var configured for {account_label}", severity="warning")
            return results

        token = os.getenv(token_env_var)
        if not token:
            self.notify(
                f"Token not found in environment variable {token_env_var} for {account_label}",
                severity="warning"
            )
            return results

        # Build all queries for this account
        queries = self.build_queries(account)
        api_base = account.get("api_base", "https://api.github.com")

        # Get authenticated username
        username = await self.get_authenticated_user(api_base, token, token_env_var)

        # Prepare request headers
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Fetch PRs for each query
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for query_label, query_string in queries:
                    url = f"{api_base}/search/issues"
                    params = {"q": query_string, "per_page": 100}

                    try:
                        response = await client.get(url, headers=headers, params=params)

                        if response.status_code == 200:
                            data = response.json()
                            prs = data.get("items", [])
                            results.append((account_label, username, query_label, prs))
                        else:
                            error_msg = f"API error for {account_label} ({query_label}): HTTP {response.status_code}"
                            try:
                                error_data = response.json()
                                if "message" in error_data:
                                    error_msg += f" - {error_data['message']}"
                                if "errors" in error_data:
                                    error_msg += f" - Errors: {error_data['errors']}"
                            except Exception:
                                pass
                            self.notify(error_msg, severity="error")
                            results.append((account_label, username, query_label, []))

                    except Exception as e:
                        self.notify(
                            f"Error fetching {query_label} for {account_label}: {str(e)}",
                            severity="error"
                        )
                        results.append((account_label, username, query_label, []))

        except Exception as e:
            self.notify(f"Network error for {account_label}: {str(e)}", severity="error")

        return results

    def calculate_age(self, created_at: str) -> str:
        """
        Calculate human-readable age from ISO timestamp.

        Args:
            created_at: ISO 8601 timestamp string

        Returns:
            Human-readable age string (e.g., "2h", "3d")
        """
        try:
            created = parse_date(created_at)
            now = datetime.now(timezone.utc)
            delta = now - created

            if delta.days > 0:
                return f"{delta.days}d"
            elif delta.seconds >= 3600:
                return f"{delta.seconds // 3600}h"
            elif delta.seconds >= 60:
                return f"{delta.seconds // 60}m"
            else:
                return "now"
        except Exception:
            return "?"

    def extract_repo_name(self, repo_url: str) -> str:
        """
        Extract repository name from URL.

        Args:
            repo_url: Full repository URL

        Returns:
            Repository name in format "owner/repo"
        """
        try:
            # repo_url format: https://api.github.com/repos/owner/repo
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            return repo_url
        except Exception:
            return repo_url

    def determine_pr_status(
        self,
        pr: dict[str, Any],
        query_label: str,
        username: str,
        reviewer_info: dict[str, Any] | None = None
    ) -> tuple[Priority, str]:
        """
        Determine the priority and status of a PR.

        Args:
            pr: PR data from GitHub API
            query_label: The query label that found this PR
            username: Current user's GitHub username
            reviewer_info: Optional dict with 'requested_reviewers' and 'requested_teams' lists

        Returns:
            Tuple of (Priority, status_string)
        """
        author = pr.get("user", {}).get("login", "")
        is_my_pr = author.lower() == username.lower() if username else False

        # Check for assignment
        assignees = pr.get("assignees", [])
        is_assigned = any(a.get("login", "").lower() == username.lower() for a in assignees) if username else False

        # Check if this is a review request query
        is_review_request_query = "review-requested:@me" in query_label.lower() or "review requested" in query_label.lower()

        # Differentiate between individual and team review requests
        is_individual_review_request = False
        is_team_review_request = False

        if is_review_request_query and reviewer_info:
            # Check if user is individually requested
            requested_reviewers = reviewer_info.get("requested_reviewers", [])
            is_individual_review_request = username in requested_reviewers if username else False

            # Check if there are team requests (and user wasn't individually requested)
            requested_teams = reviewer_info.get("requested_teams", [])
            is_team_review_request = bool(requested_teams) and not is_individual_review_request
        elif is_review_request_query:
            # Fallback if reviewer_info not available (shouldn't happen normally)
            is_individual_review_request = True

        # Priority logic:
        # HIGH: Individually requested for review, or assigned to you (you're blocking others)
        if is_individual_review_request or is_assigned:
            if is_assigned and is_individual_review_request:
                return Priority.HIGH, "🔴 Action Needed"
            elif is_individual_review_request:
                return Priority.HIGH, "🔴 Review"
            else:
                return Priority.HIGH, "🔴 Assigned"

        # MEDIUM: Team review request (not individually requested)
        if is_team_review_request:
            return Priority.MEDIUM, "🟡 Team Review"

        # MEDIUM: Your PR with changes requested or needs attention
        if is_my_pr:
            # Check labels for changes requested or similar
            labels = [label.get("name", "").lower() for label in pr.get("labels", [])]
            if any(word in " ".join(labels) for word in ["changes", "requested", "wip", "blocked"]):
                return Priority.MEDIUM, "🟡 Changes Needed"

            # Check if it's approved (we can infer from query or check later)
            if "approved" in query_label.lower():
                return Priority.LOW, "🟢 Approved"

            # Default for user's PRs
            return Priority.LOW, "🟢 Waiting"

        # LOW: Everything else (watching, mentioned, etc.)
        return Priority.LOW, "⚪ Watching"

    async def refresh_data(self) -> None:
        """Fetch PRs from all configured accounts and update the table."""
        if not self.config or not self.config.get("accounts"):
            return

        self.pr_urls.clear()

        # Update status
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update("🔄 Fetching PRs...")

        accounts = self.config.get("accounts", [])

        # Fetch PRs from all accounts concurrently
        all_results = []
        for account in accounts:
            account_results = await self.fetch_prs(account)
            all_results.extend(account_results)

        # Process PRs and collect them with priority info, grouped by query label
        pr_rows_by_query = {}  # query_label -> [row_data]
        seen_prs = set()  # Track PR IDs to avoid duplicates across queries

        for account_label, username, query_label, prs in all_results:
            if query_label not in pr_rows_by_query:
                pr_rows_by_query[query_label] = []

            for pr in prs:
                pr_id = pr["id"]

                # Skip if we've already added this PR (can happen with overlapping queries)
                if pr_id in seen_prs:
                    continue
                seen_prs.add(pr_id)

                # Determine priority and status
                priority, status = self.determine_pr_status(pr, query_label, username)

                # Determine state - use query label, with draft override
                state = query_label
                if pr.get("draft", False):
                    state = f"{query_label} (Draft)"

                # Extract data
                repo_name = self.extract_repo_name(pr["repository_url"])
                title = pr["title"]
                author = pr["user"]["login"]
                age = self.calculate_age(pr["created_at"])
                pr_url = pr["html_url"]

                # Collect row data with priority for sorting
                row_key = f"{account_label}_{pr_id}"
                row_data = {
                    "priority": priority,
                    "status": status,
                    "account": account_label,
                    "account_username": username,  # Store for check fetching
                    "state": state,
                    "repo": repo_name,
                    "title": title,
                    "author": author,
                    "age": age,
                    "url": pr_url,
                    "key": row_key,
                    "checks": "⚪",  # Default, will be updated
                    "pr": pr,  # Store PR object for check fetching
                    "original_query_label": query_label,  # Store for priority re-evaluation
                    "assignees": pr.get("assignees", []),  # Store for priority re-evaluation
                    "query_label": query_label,  # Store query label for grouping
                }
                pr_rows_by_query[query_label].append(row_data)

        # Flatten all rows for check status fetching
        all_pr_rows = []
        for rows in pr_rows_by_query.values():
            all_pr_rows.extend(rows)

        # Fetch check statuses concurrently for all PRs
        if all_pr_rows:
            # Build account credentials map
            account_creds = {}
            for account in accounts:
                account_label = account.get("label", account.get("id", "Unknown"))
                token_env_var = account.get("token_env_var")
                if token_env_var:
                    token = os.getenv(token_env_var)
                    if token:
                        api_base = account.get("api_base", "https://api.github.com")
                        account_creds[account_label] = {
                            "token": token,
                            "api_base": api_base,
                            "headers": {
                                "Authorization": f"token {token}",
                                "Accept": "application/vnd.github.v3+json",
                            }
                        }

            # Fetch all check statuses concurrently
            async with httpx.AsyncClient(timeout=10.0) as client:
                for row_data in all_pr_rows:
                    account_label = row_data["account"]
                    if account_label in account_creds:
                        creds = account_creds[account_label]
                        check_status, reviewer_info = await self.get_check_status(
                            row_data["pr"],
                            creds["headers"],
                            client
                        )
                        row_data["checks"] = check_status
                        row_data["reviewer_info"] = reviewer_info

        # Update priority based on reviewer info and check status
        for row_data in all_pr_rows:
            username = row_data.get("account_username", "")
            author = row_data["author"]
            is_my_pr = author.lower() == username.lower() if username else False

            # Re-determine priority with reviewer info (if available)
            if "reviewer_info" in row_data:
                # Re-evaluate priority with full reviewer information
                priority, status = self.determine_pr_status(
                    {"user": {"login": author}, "assignees": row_data.get("assignees", [])},
                    row_data.get("original_query_label", ""),
                    username,
                    row_data["reviewer_info"]
                )
                row_data["priority"] = priority
                row_data["status"] = status

            # If it's your PR and checks are failing, elevate to HIGH priority
            if is_my_pr and row_data["checks"] == "❌":
                row_data["priority"] = Priority.HIGH
                row_data["status"] = "🔴 Checks Failing"

            # Clean up temporary fields
            row_data.pop("pr", None)
            row_data.pop("account_username", None)
            row_data.pop("reviewer_info", None)
            row_data.pop("assignees", None)
            row_data.pop("original_query_label", None)

        # Sort PRs within each query by priority
        for query_label in pr_rows_by_query:
            pr_rows_by_query[query_label].sort(key=lambda x: (x["priority"], x["age"]))

        # Clear and rebuild the main container
        main_container = self.query_one("#main-container", Container)
        await main_container.remove_children()

        # Create a section for each query label
        total_prs = 0
        for query_label, pr_rows in pr_rows_by_query.items():
            if not pr_rows:
                continue

            # Create query title
            title = Static(f"📌 {query_label} ({len(pr_rows)})", classes="query-title")

            # Create table for this query
            table = DataTable(cursor_type="row", zebra_stripes=True)
            table.add_columns(
                "Status",
                "Checks",
                "Account",
                "Type",
                "Repo",
                "Title",
                "Author",
                "Age",
            )

            # Add rows to table
            for row in pr_rows:
                table.add_row(
                    row["status"],
                    row["checks"],
                    row["account"],
                    row["state"],
                    row["repo"],
                    row["title"],
                    row["author"],
                    row["age"],
                    key=row["key"],
                )

                # Store URL for this row
                self.pr_urls[row["key"]] = row["url"]
                total_prs += 1

            # Create section and mount title and table together
            section = Vertical(title, table, classes="query-section")
            await main_container.mount(section)

        # Update status bar
        self.last_update = datetime.now()
        status_text = f"📊 {total_prs} PRs | Last updated: {self.last_update.strftime('%H:%M:%S')}"
        status_bar.update(status_text)

        self.notify(f"Dashboard updated: {total_prs} PRs found")

    def action_refresh(self) -> None:
        """Handle refresh action."""
        self.run_worker(self.refresh_data())

    def action_open_pr(self) -> None:
        """Open the selected PR in the default browser."""
        # Find the focused DataTable widget
        focused = self.focused
        if not isinstance(focused, DataTable):
            # Try to find any DataTable with a cursor
            tables = self.query(DataTable)
            for table in tables:
                if table.cursor_row is not None:
                    focused = table
                    break

        if not isinstance(focused, DataTable):
            self.notify("No PR selected", severity="warning")
            return

        table = focused

        if table.cursor_row is None:
            self.notify("No PR selected", severity="warning")
            return

        # Get the row key
        try:
            row_key = table.get_row_at(table.cursor_row)
            if not row_key:
                return

            # Find the actual key by looking at the coordinate
            cursor_coord = table.cursor_coordinate
            if cursor_coord and cursor_coord.row < len(table.rows):
                actual_key = list(table.rows.keys())[cursor_coord.row]
                pr_url = self.pr_urls.get(actual_key)

                if pr_url:
                    webbrowser.open(pr_url)
                    self.notify(f"Opening: {pr_url}")
                else:
                    self.notify("URL not found for selected PR", severity="error")
        except Exception as e:
            self.notify(f"Error opening PR: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (when Enter is pressed or row is clicked)."""
        self.action_open_pr()


def main():
    """Main entry point for the application."""
    app = PRDashboard()
    app.run()


if __name__ == "__main__":
    main()
