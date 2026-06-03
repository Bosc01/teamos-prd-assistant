"""Cluster processed issue insights into topic groups."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_FILE = ROOT / "data" / "processed" / "insights.json"
CLUSTERED_FILE = ROOT / "data" / "processed" / "clustered_insights.json"
CLUSTER_SUMMARY_FILE = ROOT / "output" / "topic_clusters.csv"

CUSTOM_STOP_WORDS = [
    "terraform", "hashicorp", "github", "issue", "issues", "http", "https",
    "com", "html", "www", "index", "description", "expected", "behavior",
    "actual", "steps", "reproduce", "additional", "context", "example",
    "using", "used", "use", "would", "like", "want", "need", "get", "got",
    "getting", "also", "one", "new", "add", "added", "adding", "currently",
    "feature", "request", "requests", "bug", "docs", "question", "relates",
    "community", "comments", "template", "reproduce", "version", "versions",
    "provider", "providers", "resource", "resources", "aws", "config",
    "configuration"
]
combined_stop_words = list(ENGLISH_STOP_WORDS) + CUSTOM_STOP_WORDS


def _clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\b[a-z0-9]\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _combined_text(issue: Dict[str, Any]) -> str:
    title = str(issue.get("title", "")).strip()
    snippet = str(issue.get("body_snippet", "")).strip()
    combined = f"{title} {snippet}".strip()
    cleaned = _clean_text(combined)
    return cleaned or "empty"


def _cluster_labels(kmeans: KMeans, feature_names: List[str]) -> Dict[int, str]:
    labels: Dict[int, str] = {}

    for cluster_id, centroid in enumerate(kmeans.cluster_centers_):
        top_indices = centroid.argsort()[-3:][::-1]
        top_terms = [feature_names[index] for index in top_indices]
        labels[cluster_id] = " ".join(top_terms)

    return labels


def _cluster_summary_rows(clustered_insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: DefaultDict[int, List[Dict[str, Any]]] = defaultdict(list)
    for issue in clustered_insights:
        grouped[int(issue["cluster_id"])].append(issue)

    rows: List[Dict[str, Any]] = []
    for cluster_id, issues in grouped.items():
        issue_count = len(issues)
        avg_signal_score = sum(float(issue.get("signal_score", 0) or 0) for issue in issues) / issue_count

        top_issues = sorted(
            issues,
            key=lambda issue: float(issue.get("signal_score", 0) or 0),
            reverse=True,
        )[:3]
        top_issue_titles = [str(issue.get("title", "")).strip() for issue in top_issues if issue.get("title")]

        rows.append(
            {
                "cluster_id": cluster_id,
                "topic_label": issues[0]["topic_cluster"],
                "issue_count": issue_count,
                "avg_signal_score": round(avg_signal_score, 2),
                "top_issues": " | ".join(top_issue_titles),
            }
        )

    return sorted(rows, key=lambda row: int(row["cluster_id"]))


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    print("Topic clusters discovered:")
    for index, row in enumerate(rows, start=1):
        print(
            f"{index}. {row['topic_label']} — {row['issue_count']} issues, "
            f"avg signal: {float(row['avg_signal_score']):.1f}"
        )

    top_by_volume = sorted(rows, key=lambda row: int(row["issue_count"]), reverse=True)[:5]
    print("Top 5 clusters by issue volume:")
    for index, row in enumerate(top_by_volume, start=1):
        print(
            f"{index}. {row['topic_label']} — {row['issue_count']} issues, "
            f"avg signal: {float(row['avg_signal_score']):.1f}"
        )

    top_by_signal = sorted(rows, key=lambda row: float(row["avg_signal_score"]), reverse=True)[:5]
    print("Top 5 clusters by avg signal score:")
    for index, row in enumerate(top_by_signal, start=1):
        print(
            f"{index}. {row['topic_label']} — {row['issue_count']} issues, "
            f"avg signal: {float(row['avg_signal_score']):.1f}"
        )


def cluster_topics(n_clusters: int = 15) -> None:
    if not PROCESSED_FILE.exists():
        raise FileNotFoundError(f"Processed insights file not found: {PROCESSED_FILE}")

    insights: List[Dict[str, Any]] = json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
    if not insights:
        raise ValueError("No insights found to cluster.")

    cluster_count = min(n_clusters, len(insights))
    documents = [_combined_text(issue) for issue in insights]

    vectorizer = TfidfVectorizer(stop_words=combined_stop_words, ngram_range=(1, 2), max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(documents)

    kmeans = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
    cluster_ids = kmeans.fit_predict(tfidf_matrix)

    feature_names = list(vectorizer.get_feature_names_out())
    labels = _cluster_labels(kmeans, feature_names)

    clustered_insights: List[Dict[str, Any]] = []
    for issue, cluster_id in zip(insights, cluster_ids):
        enriched_issue = dict(issue)
        enriched_issue["cluster_id"] = int(cluster_id)
        enriched_issue["topic_cluster"] = labels[int(cluster_id)]
        clustered_insights.append(enriched_issue)

    CLUSTERED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLUSTERED_FILE.write_text(json.dumps(clustered_insights, indent=2), encoding="utf-8")

    summary_rows = _cluster_summary_rows(clustered_insights)
    CLUSTER_SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CLUSTER_SUMMARY_FILE.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["cluster_id", "topic_label", "issue_count", "avg_signal_score", "top_issues"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    _print_summary(summary_rows)


def main() -> None:
    cluster_topics()


if __name__ == "__main__":
    main()
