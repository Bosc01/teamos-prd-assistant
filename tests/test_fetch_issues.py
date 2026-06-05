from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import fetch_issues


class _MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FetchIssuesTests(unittest.TestCase):
    def test_fetch_all_issues_writes_paginated_results(self) -> None:
        first_page = [
            {"number": 1, "title": "Issue one"},
            {"number": 2, "title": "Issue two"},
        ]
        second_page = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_raw = Path(temp_dir) / "data" / "raw"

            with mock.patch.object(fetch_issues, "RAW_DIR", temp_raw), mock.patch.object(
                fetch_issues, "_require_token", return_value="token"
            ), mock.patch("fetch_issues.requests.get") as mock_get:
                mock_get.side_effect = [_MockResponse(first_page), _MockResponse(second_page)]
                fetch_issues.fetch_all_issues(repos=["acme/widgets"])

            out_path = temp_raw / "acme_widgets_issues.json"
            self.assertTrue(out_path.exists())
            rows = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(rows, first_page)
            self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
