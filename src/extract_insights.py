"""Extract structured product insights from raw GitHub issue data."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fetch_issues import repo_output_filename, resolve_repos

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

CATEGORY_KEYWORDS = {
    "bug": ["bug", "regression", "panic", "crash", "error", "fix", "broken", "incorrect", "wrong", "unexpected"],
    "feature-request": ["feature", "enhancement", "request", "proposal", "rfe", "new", "add", "support"],
    "docs": ["doc", "docs", "documentation", "readme", "example", "guide", "typo"],
    "question": ["question", "help", "how", "usage", "support"],
}


def _category_from_labels(labels: List[str]) -> str:
    lowered = [label.lower() for label in labels]
    combined = " ".join(lowered)

    if any(keyword in combined for keyword in CATEGORY_KEYWORDS["bug"]):
        return "bug"
    if any(keyword in combined for keyword in CATEGORY_KEYWORDS["feature-request"]):
        return "feature-request"
    if any(keyword in combined for keyword in CATEGORY_KEYWORDS["docs"]):
        return "docs"
    if any(keyword in combined for keyword in CATEGORY_KEYWORDS["question"]):
        return "question"
    return "uncategorized"


def _snippet(body: str | None) -> str:
    text = (body or "").replace("\n", " ").replace("\r", " ").strip()
    return text[:300]


def _signal_score(comments: int, upvotes: int, created_at_raw: str) -> float:
    created_at = datetime.now(timezone.utc)
    if created_at_raw:
        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except ValueError:
            created_at = datetime.now(timezone.utc)

    age_days = max(0, (datetime.now(timezone.utc) - created_at).days)
    recency_weight = 1.0 / (1.0 + math.log1p(age_days / 365))
    return round((math.log1p(comments) + math.log1p(upvotes) * 2) * recency_weight, 4)


def _extract_issue(issue: Dict, repo: str) -> Dict:
    labels = [label.get("name", "") for label in issue.get("labels", []) if label.get("name")]
    upvotes = issue.get("reactions", {}).get("+1", 0)
    comments = issue.get("comments", 0)
    title = issue.get("title", "")
    created_at = issue.get("created_at", "")

    return {
        "id": issue.get("number"),
        "repo": repo,
        "title": title,
        "url": issue.get("html_url", ""),
        "state": issue.get("state", ""),
        "created_at": created_at,
        "author": issue.get("user", {}).get("login", ""),
        "labels": ", ".join(labels),
        "comments": comments,
        "upvotes": upvotes,
        "signal_score": _signal_score(comments=comments, upvotes=upvotes, created_at_raw=created_at),
        "body_snippet": _snippet(issue.get("body")),
        "category": _category_from_labels(labels + [title]),
    }


def extract_insights(repos: List[str] | None = None) -> None:
    insights: List[Dict] = []
    repo_counts: Dict[str, int] = {}
    category_counts: Counter = Counter()
    selected_repos = resolve_repos(repos)

    for repo in selected_repos:
        path = RAW_DIR / repo_output_filename(repo)
        if not path.exists():
            raise FileNotFoundError(f"Raw issue file not found: {path}")

        raw_issues = json.loads(path.read_text(encoding="utf-8"))
        repo_insights = [_extract_issue(issue, repo) for issue in raw_issues]

        insights.extend(repo_insights)
        repo_counts[repo] = len(repo_insights)
        category_counts.update(item["category"] for item in repo_insights)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "insights.json"
    out_path.write_text(json.dumps(insights, indent=2), encoding="utf-8")

    print("Processed issues by repo:")
    for repo, count in repo_counts.items():
        print(f"- {repo}: {count}")

    print("Category breakdown:")
    for category, count in sorted(category_counts.items()):
        print(f"- {category}: {count}")


if __name__ == "__main__":
    extract_insights()
