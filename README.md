# teamos-prd-assistant

This project ingests open GitHub Issues from `hashicorp/terraform` and `hashicorp/terraform-provider-aws`, extracts rule-based product insight fields, and exports a spreadsheet-ready CSV for PM workflows.

## Setup

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy environment template and set your token:
   ```bash
   cp .env.example .env
   ```
4. Edit `.env` and set `GITHUB_TOKEN`.

## Create a GitHub PAT

1. Go to GitHub **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. Generate a new token with `public_repo` scope.
3. Copy it into `.env` as `GITHUB_TOKEN=...`.

## Run the pipeline

```bash
python src/pipeline.py
```

You can override the default number of topic clusters:

```bash
python src/pipeline.py --clusters 20
```

Or via environment variable:

```bash
TOPIC_CLUSTER_COUNT=20 python src/pipeline.py
```

## Output

The pipeline writes:

- `output/insights.csv` sorted by highest `signal_score` first
- `data/processed/clustered_insights.json` with per-issue `cluster_id` and `topic_cluster`
- `output/topic_clusters.csv` with cluster summary rows (`cluster_id`, `topic_label`, `issue_count`, `avg_signal_score`, `top_issues`)

The clustering step now guards against empty/degenerate issue text and assigns those rows to an `insufficient detail` topic instead of forcing unstable vectors into KMeans.

## Approval Tracker

The Approval Tracker is a standalone module that lets PMs create approval requests
for PRDs, RFCs, and specs, track each approver's status, and receive automatic Slack
reminders — so you never have to manually ping people again. Every notification and
status change is logged to a full audit trail stored in `data/approvals/approvals.json`.

### Setup

Add your Slack incoming webhook URL to `.env` (optional but recommended):

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Without a webhook, all notifications are printed to stdout so the tool remains fully
usable without Slack configured.

### Quick start

```bash
# Create an approval request
python src/approval_tracker.py create \
  --title "My Feature PRD" \
  --url "https://link-to-doc" \
  --requester "@yourname" \
  --approvers "@alice" "@bob" \
  --deadline 2026-06-25

# Check status of all requests
python src/approval_tracker.py status

# Check status of a specific request
python src/approval_tracker.py status --id abc12345

# Run reminders (add this to cron: every morning at 9 am)
python src/reminder_runner.py

# Dry run — see what would be sent without sending
python src/reminder_runner.py --dry-run
```

### Approver workflow

An approver updates their status by running:

```bash
# Mark as currently reviewing
python src/approval_tracker.py update --id <request-id> --approver @yourhandle --status reviewing

# Approve the document
python src/approval_tracker.py update --id <request-id> --approver @yourhandle --status approved

# Mark as blocked (with optional note)
python src/approval_tracker.py update --id <request-id> --approver @yourhandle --status blocked \
  --note "Waiting on security review first"
```

### Cancel a request

```bash
python src/approval_tracker.py cancel --id <request-id>
```

### View full audit trail

```bash
python src/approval_tracker.py audit --id <request-id>
```

### Cron setup

To send reminders automatically every weekday morning at 9 am:

```
0 9 * * 1-5 cd /path/to/teamos-prd-assistant && python src/reminder_runner.py
```

---

## Fields reference

| Field | Description |
|---|---|
| `id` | GitHub issue number |
| `repo` | Source repository |
| `title` | Issue title |
| `url` | Issue URL |
| `state` | Issue state |
| `created_at` | Creation timestamp |
| `author` | GitHub username of issue author |
| `labels` | Comma-separated issue labels |
| `comments` | Number of issue comments |
| `upvotes` | `+1` reaction count |
| `signal_score` | `comments + (upvotes * 2)` |
| `body_snippet` | First 300 chars of body with newlines removed |
| `category` | Rule-based category from labels |
