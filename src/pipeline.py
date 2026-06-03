"""Run the GitHub Issues ingestion pipeline end-to-end."""

from __future__ import annotations

import argparse
import os

from fetch_issues import fetch_all_issues
from extract_insights import extract_insights
from export_csv import export_csv
from cluster_topics import cluster_topics


def _default_cluster_count() -> int:
    raw = os.getenv("TOPIC_CLUSTER_COUNT", "15").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 15


def run_pipeline(n_clusters: int | None = None) -> None:
    try:
        print("Step 1/4: Fetching issues...")
        fetch_all_issues()

        print("Step 2/4: Extracting insights...")
        extract_insights()

        print("Step 3/4: Exporting CSV...")
        export_csv()

        print("Step 4/4: Clustering topics...")
        cluster_topics(n_clusters=n_clusters or _default_cluster_count())

        print("Pipeline completed successfully.")
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full issue-insights pipeline.")
    parser.add_argument("--clusters", type=int, default=_default_cluster_count(), help="Number of topic clusters (default: %(default)s).")
    args = parser.parse_args()
    run_pipeline(n_clusters=args.clusters)
