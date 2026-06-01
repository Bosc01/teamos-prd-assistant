from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(input_path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def render_prd(insights: list[dict[str, Any]]) -> str:
    sections = ["# Terraform Product Insights\n"]
    for insight in insights:
        sections.append(f"## Problem area: {insight['problem_area']}")
        sections.append(f"- Key pain points: {', '.join(insight.get('key_pain_points', [])) or 'None captured'}")
        evidence = insight.get("supporting_evidence", [])
        sections.append("- Supporting evidence:")
        if evidence:
            sections.extend([f"  - \"{quote}\"" for quote in evidence])
        else:
            sections.append("  - None captured")
        sections.append(f"- Frequency of mentions: {insight.get('frequency', 0)}")
        sections.append(f"- Product implications: {insight.get('product_implications', 'TBD')}")
        sections.append("")
    return "\n".join(sections).strip() + "\n"


def save_markdown(content: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run(input_path: str | Path = "data/processed/aggregated_insights.json", output_path: str | Path = "output/prd_insights.md") -> Path:
    insights = load_json(input_path)
    return save_markdown(render_prd(insights), output_path)


if __name__ == "__main__":
    output = run()
    print(f"Saved PRD markdown to {output}")
