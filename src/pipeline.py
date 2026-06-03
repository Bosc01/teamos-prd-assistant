"""Run the GitHub Issues ingestion pipeline end-to-end."""

from __future__ import annotations

from fetch_issues import fetch_all_issues
from extract_insights import extract_insights
from export_csv import export_csv
from cluster_topics import cluster_topics


def run_pipeline() -> None:
    try:
        print("Step 1/4: Fetching issues...")
        fetch_all_issues()

        print("Step 2/4: Extracting insights...")
        extract_insights()

        print("Step 3/4: Exporting CSV...")
        export_csv()

        print("Step 4/4: Clustering topics...")
        cluster_topics()

        print("Pipeline completed successfully.")
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise


if __name__ == "__main__":
    run_pipeline()
