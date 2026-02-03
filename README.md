# GitHub PR Monitor

A unified Terminal User Interface (TUI) dashboard for monitoring Pull Requests across multiple GitHub accounts and repositories, including GitHub Enterprise instances.

## Features

- 🔍 **Multi-Account Support**: Monitor PRs from both public GitHub and GitHub Enterprise instances simultaneously
- 🎯 **Granular Filtering**: Track all repos or specify specific repositories per account
- 🎨 **Configurable Queries**: Customize what PRs to track - reviews, your PRs, assignments, mentions, and more
- 📊 **Smart Prioritization**: Automatically sorts PRs by priority - see what needs your attention first
- ✅ **CI/CD Status**: See at a glance which PRs have passing, failing, or pending checks
- ⚡ **Real-time Updates**: Auto-refresh with configurable intervals (default: 5 minutes), fetches data on launch
- 🖥️ **Terminal Native**: Fast, keyboard-driven workflow that lives in your terminal
- 🔗 **Quick Access**: Open PRs directly in your browser with a single keystroke
- 🔒 **Secure**: Uses environment variables for token storage

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository

```bash
git clone <repository-url>
cd pr-monitor
```

### 3. Install dependencies

```bash
uv sync
```

This will create a virtual environment and install all required dependencies.

## Configuration

### Step 1: Create your config file

```bash
cp config.yaml.example config.yaml
```

### Step 2: Find your API URLs

#### For Public GitHub (github.com)
The API URL is always: `https://api.github.com`

#### For GitHub Enterprise
1. Log in to your GitHub Enterprise instance (e.g., `https://github.company.com`)
2. The API base URL follows this pattern: `https://github.company.com/api/v3`
3. Replace `github.company.com` with your actual enterprise domain

**Examples:**
- If your GHE is at `https://github.robotics-corp.com`, use `https://github.robotics-corp.com/api/v3`
- If your GHE is at `https://git.enterprise.com`, use `https://git.enterprise.com/api/v3`

**How to verify your API URL:**
```bash
curl -I https://github.your-company.com/api/v3
```
You should see a `200 OK` response if the URL is correct.

### Step 3: Generate Personal Access Tokens (PATs)

You need a Personal Access Token for each GitHub account you want to monitor.

#### For Public GitHub (github.com)

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a descriptive name (e.g., "PR Monitor Tool")
4. Set an expiration date (or choose "No expiration" for convenience)
5. Select the following scopes:
   - ✅ **`repo`** (Full control of private repositories)
     - This includes `repo:status`, `repo_deployment`, `public_repo`, etc.
   - ✅ **`read:org`** (Read org and team membership, if your repos are in organizations)
6. Click **"Generate token"**
7. **IMPORTANT**: Copy the token immediately (it won't be shown again!)

#### For GitHub Enterprise

1. Log in to your GitHub Enterprise instance
2. Click your profile picture → **Settings**
3. In the left sidebar, scroll down to **Developer settings** → **Personal access tokens** → **Tokens (classic)**
4. Click **"Generate new token"** → **"Generate new token (classic)"**
5. Give it a descriptive name (e.g., "PR Monitor - Work")
6. Select the same scopes as above:
   - ✅ **`repo`**
   - ✅ **`read:org`**
7. Click **"Generate token"**
8. Copy the token immediately

**Token Format**: Tokens start with `ghp_` followed by alphanumeric characters (e.g., `ghp_abc123def456...`)

### Step 4: Set up environment variables

Add your tokens to your shell environment. Choose one of the following methods:

#### Option A: Add to your shell profile (Recommended)

Add these lines to your `~/.bashrc`, `~/.zshrc`, or equivalent:

```bash
# GitHub Personal Access Tokens for PR Monitor
export GH_PUBLIC_TOKEN="ghp_your_public_github_token_here"
export GH_WORK_TOKEN="ghp_your_enterprise_token_here"
```

Then reload your shell:
```bash
source ~/.bashrc  # or ~/.zshrc
```

#### Option B: Set temporarily for current session

```bash
export GH_PUBLIC_TOKEN="ghp_your_public_github_token_here"
export GH_WORK_TOKEN="ghp_your_enterprise_token_here"
```

**Note**: These will only last until you close your terminal.

#### Option C: Use a `.env` file (requires additional setup)

Create a `.env` file in the project directory:
```bash
GH_PUBLIC_TOKEN=ghp_your_public_github_token_here
GH_WORK_TOKEN=ghp_your_enterprise_token_here
```

Then load it before running:
```bash
source .env
```

### Step 5: Configure accounts in config.yaml

Edit your `config.yaml` file:

```yaml
accounts:
  - id: "personal"
    label: "GitHub Public"
    api_base: "https://api.github.com"
    token_env_var: "GH_PUBLIC_TOKEN"  # Must match your environment variable name
    filters:
      scope: "all"  # Track all repos

  - id: "work"
    label: "Work Enterprise"
    api_base: "https://github.your-company.com/api/v3"  # Your actual GHE domain
    token_env_var: "GH_WORK_TOKEN"  # Must match your environment variable name
    filters:
      scope: "specific"  # Only track specific repos
      repos:
        - "organization/repo-1"
        - "organization/repo-2"
```

**Filter Options:**
- `scope: "all"` - Shows PRs from all repositories you have access to
- `scope: "specific"` - Only shows PRs from the repos listed in the `repos` array

### Step 6: Configure custom queries (Optional)

By default, the tool shows PRs where you're requested as a reviewer. You can customize this to track different types of PRs using the `queries` configuration.

#### Basic Example: Track your own PRs

```yaml
accounts:
  - id: "personal"
    label: "GitHub Public"
    api_base: "https://api.github.com"
    token_env_var: "GH_PUBLIC_TOKEN"
    filters:
      scope: "all"
      queries:
        # PRs where you're requested as a reviewer
        - label: "Review Requested"
          query: "is:pr is:open review-requested:@me"
        # PRs you created
        - label: "My PRs"
          query: "is:pr is:open author:@me"
```

#### Advanced Example: Multiple query types

```yaml
accounts:
  - id: "work"
    label: "Work"
    api_base: "https://github.company.com/api/v3"
    token_env_var: "GH_WORK_TOKEN"
    filters:
      scope: "specific"
      repos:
        - "org/important-repo"
      queries:
        # PRs waiting for your review
        - label: "Review Requested"
          query: "is:pr is:open review-requested:@me"
        # Your PRs that need changes
        - label: "Changes Requested"
          query: "is:pr is:open author:@me review:changes-requested"
        # Your approved PRs waiting to merge
        - label: "Approved"
          query: "is:pr is:open author:@me review:approved"
        # PRs assigned to you
        - label: "Assigned"
          query: "is:pr is:open assignee:@me"
```

#### Common Query Patterns

Here are some useful query patterns you can use:

| Use Case | Query |
|----------|-------|
| PRs requesting your review | `is:pr is:open review-requested:@me` |
| PRs you created | `is:pr is:open author:@me` |
| PRs assigned to you | `is:pr is:open assignee:@me` |
| PRs where you're mentioned | `is:pr is:open mentions:@me` |
| Your draft PRs | `is:pr is:open is:draft author:@me` |
| PRs with changes requested (yours) | `is:pr is:open author:@me review:changes-requested` |
| Approved PRs (yours) | `is:pr is:open author:@me review:approved` |
| PRs with specific labels | `is:pr is:open label:urgent label:bug` |
| PRs from a specific user | `is:pr is:open author:username` |
| PRs needing any review | `is:pr is:open review:none` |
| Combine conditions with OR | `is:pr is:open (review-requested:@me OR assignee:@me)` |

**Note**: The `scope` filter (all/specific repos) applies to all queries within an account.

For complete GitHub search syntax, see: [GitHub Search Documentation](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)

## Usage

### Run the dashboard

```bash
uv run pr-monitor
```

Or activate the virtual environment first:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pr-monitor
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate up/down through PRs |
| `Enter` | Open selected PR in your default browser |
| `R` | Force refresh (fetch latest PRs) |
| `Q` | Quit the application |

## Understanding the Dashboard

The dashboard displays a table with the following columns:

| Column | Description |
|--------|-------------|
| **Status** | Priority indicator showing what needs your attention:<br>🔴 **High Priority** - Review requested, assigned to you, **your PRs with failing checks**, or action needed<br>🟡 **Medium Priority** - Your PRs with changes requested<br>🟢 **Low Priority** - Your PRs waiting for review, or approved PRs<br>⚪ **Watching** - PRs you're mentioned in or monitoring |
| **Checks** | CI/CD check status:<br>✅ **Passing** - All checks successful<br>❌ **Failing** - One or more checks failed (**automatically elevates your PRs to high priority**)<br>🟡 **Pending** - Checks in progress or queued<br>⚪ **None** - No checks configured or status unavailable |
| **Account** | Which account/instance this PR is from (e.g., "GitHub Public", "Work") |
| **Type** | The query type/label (e.g., "Review Requested", "My PRs", "Changes Requested"). Shows "(Draft)" suffix for draft PRs |
| **Repo** | Repository name in format "owner/repo" |
| **Title** | PR title (may be truncated for long titles) |
| **Author** | GitHub username of the PR author |
| **Age** | How long ago the PR was created (e.g., "2h", "3d") |

### PR Organization and Sorting

PRs are automatically sorted by priority to help you focus on what needs attention:

1. **🔴 High Priority PRs** appear first - These need your immediate action:
   - Review requests where you're blocking someone
   - PRs assigned to you
   - **Your PRs with failing CI/CD checks** (marked as "🔴 Checks Failing")
   - PRs marked as "Action Needed"

2. **🟡 Medium Priority PRs** appear next - Your PRs that need work:
   - PRs with changes requested
   - PRs marked as WIP or blocked

3. **🟢 Low Priority PRs** appear last - Items you're tracking:
   - Your PRs waiting for review
   - Approved PRs waiting to merge
   - PRs you're mentioned in or watching

Within each priority level, PRs are sorted by age (newest first).

**Smart Check-Based Prioritization**: The tool automatically elevates your PRs with failing checks to high priority, ensuring you fix broken builds before they block others!

The status bar at the bottom shows:
- Total number of PRs found
- Last update timestamp

## Troubleshooting

### "config.yaml not found!"
- Make sure you've copied `config.yaml.example` to `config.yaml`
- Check that you're running the command from the project directory

### "Token not found in environment variable"
- Verify your environment variables are set: `echo $GH_PUBLIC_TOKEN`
- Make sure the variable names in `config.yaml` match exactly
- If you added them to your shell profile, reload it: `source ~/.bashrc`

### "API error: HTTP 401"
- Your token is invalid or expired
- Regenerate the token following the steps above
- Make sure you're using a "classic" token, not a fine-grained token

### "API error: HTTP 403"
- You've hit the rate limit (60 requests/hour for unauthenticated, 5000/hour for authenticated)
- Wait an hour or check your rate limit status:
  ```bash
  curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/rate_limit
  ```

### "Network error" or connection timeout
- For GitHub Enterprise: Make sure you're connected to VPN if required
- Check that your API URL is correct: `curl -I <your-api-url>`
- Verify you can access the GitHub instance in your browser

### No PRs showing up
- Verify you have PRs with review requests: Check on GitHub web interface
- Check your filter configuration in `config.yaml`
- Try changing `scope: "specific"` to `scope: "all"` temporarily to see if it's a filter issue

### PRs from only one account showing
- Check the notifications in the app (they appear briefly at the bottom)
- Verify tokens for all accounts are set correctly
- Make sure API URLs are correct for each account

## Advanced Configuration

### Customize refresh interval

In `config.yaml`:
```yaml
general:
  refresh_interval_seconds: 180  # Refresh every 3 minutes
```

### Monitor multiple PR types simultaneously

You can add multiple queries per account to see different types of PRs side-by-side:

```yaml
accounts:
  - id: "work"
    label: "Work"
    api_base: "https://github.company.com/api/v3"
    token_env_var: "GH_WORK_TOKEN"
    filters:
      scope: "all"
      queries:
        # All three will be displayed together in the dashboard
        - label: "Review Requested"
          query: "is:pr is:open review-requested:@me"
        - label: "My PRs"
          query: "is:pr is:open author:@me"
        - label: "Mentioned"
          query: "is:pr is:open mentions:@me"
```

See [Step 6: Configure custom queries](#step-6-configure-custom-queries-optional) for more query examples.

## Development

### Running in development mode

```bash
uv run python -m pr_monitor.app
```

### Project structure

```
pr-monitor/
├── pr_monitor/
│   ├── __init__.py
│   └── app.py           # Main application
├── config.yaml.example  # Example configuration
├── config.yaml         # Your configuration (not in git)
├── pyproject.toml      # Project dependencies
└── README.md           # This file
```

## Security Notes

- **Never commit your `config.yaml`** with real tokens to version control
- Tokens in `config.yaml.example` are placeholders only
- Use environment variables for token storage
- Rotate your tokens periodically
- Use the minimum required scopes for your tokens

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you encounter issues:
1. Check the Troubleshooting section above
2. Verify your configuration against `config.yaml.example`
3. Open an issue on GitHub with:
   - Your operating system
   - Python version (`python --version`)
   - Error messages (with tokens redacted)
   - Steps to reproduce

---

**Note**: This tool only reads PR information and opens URLs. It does not modify your repositories or leave comments.
