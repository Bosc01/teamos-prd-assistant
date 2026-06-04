from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from unittest import mock

import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import export_csv  # noqa: E402


class ExportCsvTests(unittest.TestCase):
    def test_export_csv_writes_sorted_rows_with_headers(self) -> None:
        insights = [
            {"id": 1, "repo": "a/b", "title": "one", "url": "", "state": "open", "created_at": "", "author": "", "labels": "", "comments": 1, "upvotes": 0, "signal_score": 1.2, "body_snippet": "", "category": "bug"},
            {"id": 2, "repo": "a/b", "title": "two", "url": "", "state": "open", "created_at": "", "author": "", "labels": "", "comments": 1, "upvotes": 0, "signal_score": 5.0, "body_snippet": "", "category": "bug"},
            {"id": 3, "repo": "a/b", "title": "three", "url": "", "state": "open", "created_at": "", "author": "", "labels": "", "comments": 1, "upvotes": 0, "signal_score": 3.1, "body_snippet": "", "category": "bug"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            processed_file = temp_root / "data" / "processed" / "insights.json"
            output_file = temp_root / "output" / "insights.csv"
            processed_file.parent.mkdir(parents=True, exist_ok=True)
            processed_file.write_text(json.dumps(insights), encoding="utf-8")

            with mock.patch.object(export_csv, "PROCESSED_FILE", processed_file), mock.patch.object(
                export_csv, "OUTPUT_FILE", output_file
            ):
                export_csv.export_csv()

            self.assertTrue(output_file.exists())
            with output_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, export_csv.CSV_FIELDS)

            self.assertEqual(len(rows), 3)
            scores = [float(row["signal_score"]) for row in rows]
            self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
