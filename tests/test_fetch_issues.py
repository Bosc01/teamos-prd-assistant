from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import fetch_issues


class _MockResponse:
    def __init__(self, payload, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

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
            ), mock.patch("src.fetch_issues.requests.get") as mock_get:
                mock_get.side_effect = [_MockResponse(first_page), _MockResponse(second_page)]
                fetch_issues.fetch_all_issues(repos=["acme/widgets"])

            out_path = temp_raw / "acme_widgets_issues.json"
            self.assertTrue(out_path.exists())
            rows = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(rows, first_page)
            self.assertEqual(mock_get.call_count, 2)

    def test_fetch_repo_issues_drops_prs_and_accumulates_pages(self) -> None:
        first_page = [
            {"number": 1, "title": "Issue one"},
            {"number": 2, "title": "A pull request", "pull_request": {"url": "https://example.com/pr/2"}},
        ]
        second_page = [{"number": 3, "title": "Issue three"}]
        third_page: list = []

        with mock.patch("src.fetch_issues.requests.get") as mock_get:
            mock_get.side_effect = [
                _MockResponse(first_page),
                _MockResponse(second_page),
                _MockResponse(third_page),
            ]
            with mock.patch("builtins.print"):
                issues = fetch_issues._fetch_repo_issues("acme/widgets", "token")

        self.assertEqual([issue["number"] for issue in issues], [1, 3])
        self.assertEqual(mock_get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
