from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(input_path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def save_json(payload: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def aggregate_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "problem_area": "",
            "classification": "",
            "frequency": 0,
            "key_pain_points": [],
            "supporting_evidence": [],
            "product_implications": "",
        }
    )

    for post in posts:
        topic = post.get("topic", "general")
        classification = post.get("classification", "question")
        key = (topic, classification)
        group = grouped[key]
        group["problem_area"] = topic
        group["classification"] = classification
        group["frequency"] += 1
        summary = post.get("summary") or post.get("title", "")
        if summary and summary not in group["key_pain_points"]:
            group["key_pain_points"].append(summary)
        quote = post.get("body") or post.get("title", "")
        if quote:
            group["supporting_evidence"].append(quote[:240])

    results: list[dict[str, Any]] = []
    for group in grouped.values():
        group["supporting_evidence"] = group["supporting_evidence"][:3]
        pain_points = group["key_pain_points"][:3]
        group["key_pain_points"] = pain_points
        group["product_implications"] = (
            f"Users discussing {group['problem_area']} often need clearer support for {group['classification']} workflows."
        )
        results.append(group)

    return sorted(results, key=lambda item: item["frequency"], reverse=True)


def run(input_path: str | Path = "data/processed/processed_posts.json", output_path: str | Path = "data/processed/aggregated_insights.json") -> Path:
    posts = load_json(input_path)
    aggregated = aggregate_posts(posts)
    return save_json(aggregated, output_path)


if __name__ == "__main__":
    output = run()
    print(f"Saved aggregated insights to {output}")
