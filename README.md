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

## Output

The pipeline writes `output/insights.csv`, sorted by highest `signal_score` first. You can open this file directly in Excel or Google Sheets.

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
