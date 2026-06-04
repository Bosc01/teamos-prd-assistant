from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import extract_insights  # noqa: E402


class ExtractInsightsTests(unittest.TestCase):
    def _issue(self, *, comments: int, upvotes: int, created_at: str, labels: list[str], title: str) -> dict:
        return {
            "number": 1,
            "title": title,
            "html_url": "https://example.com/issues/1",
            "state": "open",
            "created_at": created_at,
            "user": {"login": "alice"},
            "labels": [{"name": label} for label in labels],
            "comments": comments,
            "reactions": {"+1": upvotes},
            "body": "body",
        }

    def test_signal_score_zero_comments_zero_upvotes(self) -> None:
        issue = self._issue(
            comments=0,
            upvotes=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            labels=[],
            title="generic",
        )
        result = extract_insights._extract_issue(issue, "owner/repo")
        self.assertEqual(result["signal_score"], 0.0)

    def test_signal_score_prefers_recent_issue(self) -> None:
        now = datetime.now(timezone.utc)
        recent = self._issue(
            comments=5,
            upvotes=3,
            created_at=now.isoformat(),
            labels=[],
            title="same issue",
        )
        old = self._issue(
            comments=5,
            upvotes=3,
            created_at=(now - timedelta(days=365 * 3)).isoformat(),
            labels=[],
            title="same issue",
        )
        recent_score = extract_insights._extract_issue(recent, "owner/repo")["signal_score"]
        old_score = extract_insights._extract_issue(old, "owner/repo")["signal_score"]
        self.assertGreater(recent_score, old_score)

    def test_signal_score_comments_dominate_after_log_scaling(self) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        comment_heavy = self._issue(
            comments=10,
            upvotes=0,
            created_at=created_at,
            labels=[],
            title="comment heavy",
        )
        upvote_only = self._issue(
            comments=0,
            upvotes=1,
            created_at=created_at,
            labels=[],
            title="upvote only",
        )

        comment_score = extract_insights._extract_issue(comment_heavy, "owner/repo")["signal_score"]
        upvote_score = extract_insights._extract_issue(upvote_only, "owner/repo")["signal_score"]
        self.assertGreater(comment_score, upvote_score)

    def test_category_assignment(self) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        cases = [
            (["bug"], "any title", "bug"),
            (["enhancement"], "any title", "feature-request"),
            (["documentation"], "any title", "docs"),
            ([], "Provider crash when upgrading", "bug"),
            ([], "General feedback thread", "uncategorized"),
        ]

        for labels, title, expected in cases:
            with self.subTest(labels=labels, title=title):
                issue = self._issue(
                    comments=0,
                    upvotes=0,
                    created_at=created_at,
                    labels=labels,
                    title=title,
                )
                result = extract_insights._extract_issue(issue, "owner/repo")
                self.assertEqual(result["category"], expected)


if __name__ == "__main__":
    unittest.main()
