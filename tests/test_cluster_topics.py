from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cluster_topics  # noqa: E402


class ClusterTopicsTests(unittest.TestCase):
    def test_topic_label_deduplicates_redundant_terms(self) -> None:
        feature_names = ["data source", "data", "source", "iam role", "role"]
        term_scores = np.array([0.9, 0.85, 0.8, 0.5, 0.4])

        label = cluster_topics._topic_label_from_scores(feature_names, term_scores)

        self.assertEqual(label, "data source / iam role")

    def test_cluster_topics_handles_sparse_and_empty_documents(self) -> None:
        insights = [
            {"id": 1, "title": "", "body_snippet": "", "signal_score": 1},
            {"id": 2, "title": "S3 bucket acl issue", "body_snippet": "bucket acl policy error", "signal_score": 3},
            {"id": 3, "title": "S3 bucket acl issue", "body_snippet": "bucket acl policy error", "signal_score": 2},
            {"id": 4, "title": "IAM role drift", "body_snippet": "role policy drift state", "signal_score": 5},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            processed = temp_root / "insights.json"
            clustered = temp_root / "clustered_insights.json"
            summary = temp_root / "topic_clusters.csv"
            processed.write_text(json.dumps(insights), encoding="utf-8")

            with mock.patch.object(cluster_topics, "PROCESSED_FILE", processed), mock.patch.object(
                cluster_topics, "CLUSTERED_FILE", clustered
            ), mock.patch.object(cluster_topics, "CLUSTER_SUMMARY_FILE", summary):
                cluster_topics.cluster_topics(n_clusters=10)

            clustered_rows = json.loads(clustered.read_text(encoding="utf-8"))
            self.assertEqual(len(clustered_rows), len(insights))
            self.assertTrue(any(row["topic_cluster"] == cluster_topics.FALLBACK_TOPIC_LABEL for row in clustered_rows))
            self.assertTrue(all("cluster_id" in row for row in clustered_rows))

            repeated_word_pattern = re.compile(r"\b(\w+)\s+\1\b")
            for row in clustered_rows:
                normalized_label = row["topic_cluster"].replace("/", " ")
                self.assertIsNone(repeated_word_pattern.search(normalized_label))


if __name__ == "__main__":
    unittest.main()
