# teamos-prd-assistant

[![CI](https://github.com/Bosc01/teamos-prd-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Bosc01/teamos-prd-assistant/actions/workflows/ci.yml)

51 unit tests run in CI on Python 3.10, 3.11, and 3.12 (`make test`).

HashiCorp PMs spend significant time on work that produces nothing - chasing approvals,
repeating the same follow-ups with no record, and trying to find customer context that
lives in ten different places at once. This repo is a set of working prototypes built
during PM discovery to test whether targeted tooling can eliminate that overhead.
Built by Harekas Bindra, PM Intern, as part of the Team OS working group.

Two modules are currently functional. A third is in progress.

---

## Module 1: GitHub Signal Pipeline

Ingests open GitHub issues from HashiCorp public repos, scores each issue by signal
strength (comments, upvotes, recency), clusters into topic groups, and exports a
ranked CSV ready for PM review.

### Setup

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
5. Optional: set `ISSUE_REPOS` to a comma-separated list of repositories to override
   defaults (example: `ISSUE_REPOS=hashicorp/terraform,hashicorp/terraform-provider-aws`).

### Create a GitHub PAT

1. Go to GitHub **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. Generate a new token with `public_repo` scope.
3. Copy it into `.env` as `GITHUB_TOKEN=...`.

### Run the pipeline

```bash
python -m src.pipeline
```

You can override the default number of topic clusters:

```bash
python -m src.pipeline --clusters 20
```

Or via environment variable:

```bash
TOPIC_CLUSTER_COUNT=20 python -m src.pipeline
```

You can also override repositories per run:

```bash
python -m src.pipeline --repos hashicorp/terraform hashicorp/terraform-provider-aws
```

### Demo without a live API call

The repo ships a sample dataset in `data/samples/`: 100 open issues from
hashicorp/terraform and 100 from hashicorp/terraform-provider-aws, fetched on
2026-08-31 and redacted to the fields the pipeline reads (bodies truncated to
500 characters, email addresses removed), plus a matching `insights.json`.
Copy it into the working directories, then run everything after the fetch step:

```bash
make seed
python -m src.extract_insights
python -m src.cluster_topics --clusters 10
python -m src.export_csv
```

No `GITHUB_TOKEN` is required for any of these commands.

### Output

The pipeline writes:

- `output/insights.csv` sorted by highest `signal_score` first, including each
  issue's `cluster_id` and `topic_cluster`
- `data/processed/clustered_insights.json` with per-issue `cluster_id` and `topic_cluster`
- `output/topic_clusters.csv` with cluster summary rows (`cluster_id`, `topic_label`,
  `issue_count`, `avg_signal_score`, `top_issues`)

The clustering step guards against empty/degenerate issue text: those rows get the
sentinel `cluster_id` -1 with topic `insufficient detail`, stay out of
`topic_clusters.csv` and the volume rankings, and are reported as a coverage
statistic instead.

### What is missing

- LLM summarization of clusters (labels are TF-IDF derived, not language model generated)
- Jira connection for commercial signal alongside OSS signal
- UI layer for browsing results

---

## Module 2: Approval Tracker

PMs spend hours chasing sign-offs with no record of who was contacted or when. The
Approval Tracker lets a PM create an approval request with a doc link, approver list,
and deadline. Each approver gets a Slack notification when the request is created.
The system sends automatic reminders on a configurable schedule, and one overdue
alert per cooldown window once the deadline passes. Every notification and status
change is logged to a full audit trail in `data/approvals/approvals.json`.

Built directly from discovery findings: 15 of 17 PM interviews named stalled sign-off
workflows as a top pain point, unprompted.

### Setup

Add your Slack incoming webhook URL to `.env` (optional but recommended):

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Without a webhook, all notifications are printed to stdout so the tool remains fully
usable without Slack configured.

### Demo without any setup

Seed the sample data, which includes two approval requests with placeholder
handles (one healthy, one overdue with a blocked approver):

```bash
make seed
```

To see reminders run without sending anything:

```bash
python -m src.reminder_runner --dry-run
```

To see current approval status and the urgency-grouped dashboard:

```bash
python -m src.approval_tracker status
python -m src.approval_tracker dashboard
```

### Quick start

```bash
# Create an approval request
python -m src.approval_tracker create \
  --title "My Feature PRD" \
  --url "https://link-to-doc" \
  --requester "@yourname" \
  --approvers "@alice" "@bob" \
  --deadline 2026-06-25

# Check status of all requests
python -m src.approval_tracker status

# Check status of a specific request
python -m src.approval_tracker status --id abc12345

# Run reminders (add this to cron: every morning at 9 am)
python -m src.reminder_runner

# Dry run - see what would be sent without sending
python -m src.reminder_runner --dry-run
```

### Approver workflow

An approver updates their status by running:

```bash
# Mark as currently reviewing
python -m src.approval_tracker update --id <request-id> --approver @yourhandle --status reviewing

# Approve the document
python -m src.approval_tracker update --id <request-id> --approver @yourhandle --status approved

# Mark as blocked (with optional note)
python -m src.approval_tracker update --id <request-id> --approver @yourhandle --status blocked \
  --note "Waiting on security review first"
```

When every approver has approved, the request flips to `complete`; if an approver
later moves back to `reviewing` or `blocked`, it reopens. Cancelled requests reject
further updates.

### Cancel a request

```bash
python -m src.approval_tracker cancel --id <request-id>
```

### View full audit trail

```bash
python -m src.approval_tracker audit --id <request-id>
```

### Cron setup

To send reminders automatically every weekday morning at 9 am:

```
0 9 * * 1-5 cd /path/to/teamos-prd-assistant && python -m src.reminder_runner
```

Concurrent runs are safe: every write to `approvals.json` holds an exclusive file
lock, so a cron run and an interactive session cannot clobber each other's
audit-trail entries.

### What is missing

- Hermes integration - connect directly to the approval workflow inside Hermes
- Dashboard view of all pending approvals across the team
- A way for approvers to communicate blockers back to the requester in-thread

---

## Module 3: Document Store (in progress)

`src/doc_store.py` is a local JSON-backed store for PM knowledge artifacts - PRDs,
PRFAQs, RFCs, field notes, and customer call summaries. It supports add, search,
list, and show operations with filtering by doc type, product area, and customer.

This module is functional but not yet wired into the pipeline or the approval tracker.
It is the foundation for a future context layer that surfaces relevant prior art when
a PM starts a new document. Not ready to demo - listed here for transparency.

```bash
# Add a document
python -m src.doc_store add --title "My PRD" --url "https://..." --type prd \
  --author "@handle" --product-area "terraform-core" \
  --customers "acme" --tags "auth" --content "snippet here"

# Search documents
python -m src.doc_store search --query "authentication"

# List all PRDs
python -m src.doc_store list --type prd
```

---

## Development

```bash
pip install -r requirements-dev.txt
make test    # unittest suite
make lint    # ruff
make seed    # copy data/samples/ into the working data directories
```

Runtime dependencies are pinned in `requirements.txt`; `requirements-dev.txt` adds
lint tooling. CI runs lint and the full suite on Python 3.10, 3.11, and 3.12.
Licensed under the MIT License.

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
| `signal_score` | Log-scaled comments/upvotes with 180-day half-life recency decay |
| `body_snippet` | First 300 chars of body with newlines removed |
| `category` | Rule-based category from labels and title keywords |
| `cluster_id` | Topic cluster id (-1 means insufficient detail to cluster) |
| `topic_cluster` | TF-IDF derived topic label |
