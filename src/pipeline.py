"""Run the GitHub Issues ingestion pipeline end-to-end."""

from __future__ import annotations

import argparse
from typing import List

from config import default_cluster_count
from cluster_topics import cluster_topics
from export_csv import export_csv
from extract_insights import extract_insights
from fetch_issues import fetch_all_issues


def run_pipeline(n_clusters: int | None = None, repos: List[str] | None = None) -> None:
    try:
        print("Step 1/4: Fetching issues...")
        fetch_all_issues(repos=repos)

        print("Step 2/4: Extracting insights...")
        extract_insights(repos=repos)

        print("Step 3/4: Exporting CSV...")
        export_csv()

        print("Step 4/4: Clustering topics...")
        cluster_topics(n_clusters=n_clusters if n_clusters is not None else default_cluster_count())

        print("Pipeline completed successfully.")
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full issue-insights pipeline.")
    parser.add_argument("--clusters", type=int, default=default_cluster_count(), help="Number of topic clusters (default: %(default)s).")
    parser.add_argument("--repos", nargs="+", help="Space-separated list of owner/repo values to fetch.")
    args = parser.parse_args()
    run_pipeline(n_clusters=args.clusters, repos=args.repos)
