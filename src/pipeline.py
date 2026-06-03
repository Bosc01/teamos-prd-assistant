"""Run the GitHub Issues ingestion pipeline end-to-end."""

from __future__ import annotations

from fetch_issues import fetch_all_issues
from extract_insights import extract_insights
from export_csv import export_csv


def run_pipeline() -> None:
    try:
        print("Step 1/3: Fetching issues...")
        fetch_all_issues()

        print("Step 2/3: Extracting insights...")
        extract_insights()

        print("Step 3/3: Exporting CSV...")
        export_csv()

        print("Pipeline completed successfully.")
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise


if __name__ == "__main__":
    run_pipeline()
