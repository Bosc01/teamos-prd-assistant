"""Extract structured product insights from raw GitHub issue data."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

RAW_FILES = {
    "hashicorp/terraform": RAW_DIR / "terraform_issues.json",
    "hashicorp/terraform-provider-aws": RAW_DIR / "terraform_aws_issues.json",
}


def _category_from_labels(labels: List[str]) -> str:
    lowered = [label.lower() for label in labels]

    if any("bug" in label for label in lowered):
        return "bug"
    if any("enhancement" in label or "feature" in label for label in lowered):
        return "feature-request"
    if any("documentation" in label or "docs" in label for label in lowered):
        return "docs"
    if any("question" in label for label in lowered):
        return "question"
    return "uncategorized"


def _snippet(body: str | None) -> str:
    text = (body or "").replace("\n", " ").replace("\r", " ").strip()
    return text[:300]


def _extract_issue(issue: Dict, repo: str) -> Dict:
    labels = [label.get("name", "") for label in issue.get("labels", []) if label.get("name")]
    upvotes = issue.get("reactions", {}).get("+1", 0)
    comments = issue.get("comments", 0)

    return {
        "id": issue.get("number"),
        "repo": repo,
        "title": issue.get("title", ""),
        "url": issue.get("html_url", ""),
        "state": issue.get("state", ""),
        "created_at": issue.get("created_at", ""),
        "author": issue.get("user", {}).get("login", ""),
        "labels": ", ".join(labels),
        "comments": comments,
        "upvotes": upvotes,
        "signal_score": comments + (upvotes * 2),
        "body_snippet": _snippet(issue.get("body")),
        "category": _category_from_labels(labels),
    }


def extract_insights() -> None:
    insights: List[Dict] = []
    repo_counts: Dict[str, int] = {}
    category_counts: Counter = Counter()

    for repo, path in RAW_FILES.items():
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
