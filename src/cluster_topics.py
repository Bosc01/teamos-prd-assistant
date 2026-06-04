"""Cluster processed issue insights into topic groups."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from config import DEFAULT_N_CLUSTERS, default_cluster_count

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_FILE = ROOT / "data" / "processed" / "insights.json"
CLUSTERED_FILE = ROOT / "data" / "processed" / "clustered_insights.json"
CLUSTER_SUMMARY_FILE = ROOT / "output" / "topic_clusters.csv"
FALLBACK_TOPIC_LABEL = "insufficient detail"

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
    return _clean_text(combined)


def _is_redundant_term(term: str, selected_terms: List[str]) -> bool:
    term_tokens = set(term.split())
    for selected in selected_terms:
        selected_tokens = set(selected.split())
        if term == selected or term_tokens.issubset(selected_tokens) or selected_tokens.issubset(term_tokens):
            return True
    return False


def _topic_label_from_scores(feature_names: List[str], term_scores: np.ndarray) -> str:
    if term_scores.size == 0 or not np.isfinite(term_scores).any():
        return "misc topic"

    ranked_indices = np.argsort(term_scores)[::-1]
    candidates: List[tuple[str, float, int]] = []
    for index in ranked_indices[:20]:
        score = float(term_scores[index])
        if score <= 0:
            continue
        term = feature_names[index]
        candidates.append((term, score, len(term.split())))

    if not candidates:
        return "misc topic"

    candidates.sort(key=lambda item: (item[2], item[1]), reverse=True)

    selected_terms: List[str] = []
    for term, _, _ in candidates:
        if _is_redundant_term(term, selected_terms):
            continue
        selected_terms.append(term)
        if len(selected_terms) >= 3:
            break

    if not selected_terms:
        return "misc topic"

    return " / ".join(selected_terms)


def _cluster_labels(tfidf_matrix: Any, cluster_ids: np.ndarray, feature_names: List[str]) -> Dict[int, str]:
    labels: Dict[int, str] = {}

    for cluster_id in sorted({int(cluster_id) for cluster_id in cluster_ids}):
        cluster_matrix = tfidf_matrix[cluster_ids == cluster_id]
        term_scores = np.asarray(cluster_matrix.mean(axis=0)).ravel()
        labels[cluster_id] = _topic_label_from_scores(feature_names, term_scores)
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


def cluster_topics(n_clusters: int = DEFAULT_N_CLUSTERS) -> None:
    if not PROCESSED_FILE.exists():
        raise FileNotFoundError(f"Processed insights file not found: {PROCESSED_FILE}")

    insights: List[Dict[str, Any]] = json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
    if not insights:
        raise ValueError("No insights found to cluster.")

    cluster_count = max(1, int(n_clusters))
    documents = [_combined_text(issue) for issue in insights]
    valid_documents = [(index, document) for index, document in enumerate(documents) if document]

    clustered_assignments: Dict[int, tuple[int, str]] = {}

    if valid_documents:
        valid_indices = [index for index, _ in valid_documents]
        valid_texts = [document for _, document in valid_documents]
        vectorizer = TfidfVectorizer(stop_words=combined_stop_words, ngram_range=(1, 2), max_features=5000)

        try:
            tfidf_matrix = vectorizer.fit_transform(valid_texts)
        except ValueError as exc:
            if "empty vocabulary" not in str(exc):
                raise
            tfidf_matrix = None

        if tfidf_matrix is not None:
            non_zero_mask = np.asarray(tfidf_matrix.getnnz(axis=1) > 0).ravel()
            filtered_indices = [valid_indices[index] for index, keep in enumerate(non_zero_mask) if keep]
            filtered_texts = [valid_texts[index] for index, keep in enumerate(non_zero_mask) if keep]

            if filtered_indices:
                filtered_matrix = tfidf_matrix[non_zero_mask]
                cluster_count = min(cluster_count, len(filtered_indices), len(set(filtered_texts)))

                if cluster_count == 1:
                    cluster_ids = np.zeros(filtered_matrix.shape[0], dtype=int)
                else:
                    kmeans = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
                    cluster_ids = np.asarray(kmeans.fit_predict(filtered_matrix))

                feature_names = list(vectorizer.get_feature_names_out())
                labels = _cluster_labels(filtered_matrix, cluster_ids, feature_names)

                for issue_index, cluster_id in zip(filtered_indices, cluster_ids):
                    clustered_assignments[issue_index] = (int(cluster_id), labels[int(cluster_id)])

    fallback_indices = set(range(len(insights))) - set(clustered_assignments)
    if fallback_indices:
        fallback_cluster_id = (max(assignment[0] for assignment in clustered_assignments.values()) + 1) if clustered_assignments else 0
        for issue_index in sorted(fallback_indices):
            clustered_assignments[issue_index] = (fallback_cluster_id, FALLBACK_TOPIC_LABEL)

    clustered_insights: List[Dict[str, Any]] = []
    for issue_index, issue in enumerate(insights):
        cluster_id, topic_label = clustered_assignments[issue_index]
        enriched_issue = dict(issue)
        enriched_issue["cluster_id"] = int(cluster_id)
        enriched_issue["topic_cluster"] = topic_label
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
    parser = argparse.ArgumentParser(description="Cluster extracted issue insights into topic groups.")
    parser.add_argument("--clusters", type=int, default=default_cluster_count(), help="Number of topic clusters (default: %(default)s).")
    args = parser.parse_args()
    cluster_topics(n_clusters=args.clusters)


if __name__ == "__main__":
    main()
