# teamos-prd-assistant

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

You can also override repositories per run:

```bash
python src/pipeline.py --repos hashicorp/terraform hashicorp/terraform-provider-aws
```

### Demo without a live API call

Sample data is already in the repo. To run the pipeline from the extraction step
onward without calling the GitHub API:

```bash
# Skip fetch - run extraction, clustering, and CSV export against existing raw data
python src/extract_insights.py
python src/pipeline.py --clusters 10
```

Or to see the clustering output directly from already-processed data:

```bash
python src/cluster_topics.py
```

Sample files:
- `data/raw/terraform_issues.json` - ~450 raw issues from hashicorp/terraform
- `data/raw/terraform_aws_issues.json` - ~900 raw issues from hashicorp/terraform-provider-aws
- `data/processed/insights.json` - already-extracted insights, ready for clustering

### Output

The pipeline writes:

- `output/insights.csv` sorted by highest `signal_score` first
- `data/processed/clustered_insights.json` with per-issue `cluster_id` and `topic_cluster`
- `output/topic_clusters.csv` with cluster summary rows (`cluster_id`, `topic_label`,
  `issue_count`, `avg_signal_score`, `top_issues`)

The clustering step guards against empty/degenerate issue text and assigns those rows
to an `insufficient detail` topic instead of forcing unstable vectors into KMeans.

### What is missing

- LLM summarization of clusters (labels are TF-IDF derived, not language model generated)
- Jira connection for commercial signal alongside OSS signal
- UI layer for browsing results

---

## Module 2: Approval Tracker

PMs spend hours chasing sign-offs with no record of who was contacted or when. The
Approval Tracker lets a PM create an approval request with a doc link, approver list,
and deadline. Each approver gets a Slack notification. The system sends automatic
reminders on a configurable schedule. Every notification and status change is logged
to a full audit trail in `data/approvals/approvals.json`.

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

A real approval request is already stored in `data/approvals/approvals.json`.
To see reminders run without sending anything:

```bash
python src/reminder_runner.py --dry-run
```

To see current approval status:

```bash
python src/approval_tracker.py status
```

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

# Dry run - see what would be sent without sending
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
python src/doc_store.py add --title "My PRD" --url "https://..." --type prd \
  --author "@handle" --product-area "terraform-core" \
  --customers "acme" --tags "auth" --content "snippet here"

# Search documents
python src/doc_store.py search --query "authentication"

# List all PRDs
python src/doc_store.py list --type prd
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
| `signal_score` | Log-scaled comments/upvotes weighted by issue recency |
| `body_snippet` | First 300 chars of body with newlines removed |
| `category` | Rule-based category from labels and title keywords |
