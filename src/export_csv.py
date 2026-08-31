"""Export processed issue insights to CSV for spreadsheet tools."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_FILE = ROOT / "data" / "processed" / "insights.json"
CLUSTERED_FILE = ROOT / "data" / "processed" / "clustered_insights.json"
OUTPUT_FILE = ROOT / "output" / "insights.csv"

CSV_FIELDS = [
    "id",
    "repo",
    "title",
    "url",
    "state",
    "created_at",
    "author",
    "labels",
    "comments",
    "upvotes",
    "signal_score",
    "body_snippet",
    "category",
    "cluster_id",
    "topic_cluster",
]


def export_csv() -> None:
    # Prefer the clustered file so the export carries cluster_id/topic_cluster;
    # fall back to the pre-clustering insights when clustering has not run.
    source_file = CLUSTERED_FILE if CLUSTERED_FILE.exists() else PROCESSED_FILE
    if not source_file.exists():
        raise FileNotFoundError(f"Processed insights file not found: {source_file}")

    insights: List[Dict] = json.loads(source_file.read_text(encoding="utf-8"))
    sorted_insights = sorted(insights, key=lambda row: row.get("signal_score", 0), reverse=True)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(sorted_insights)

    print(f"Exported {len(sorted_insights)} insights to output/insights.csv")


if __name__ == "__main__":
    export_csv()
