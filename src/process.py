from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

PROMPTS_DIR = Path("prompts")
LLM_URL = os.getenv("TEAMOS_OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
LLM_MODEL = os.getenv("TEAMOS_OPENAI_MODEL", "gpt-4o-mini")
LLM_API_KEY = os.getenv("TEAMOS_OPENAI_API_KEY", "")

CATEGORY_KEYWORDS = {
    "bug": ["bug", "broken", "error", "fails", "failure", "issue", "crash", "problem"],
    "feature request": ["feature", "request", "support", "add", "enhancement", "would like", "wish"],
    "question": ["how", "why", "what", "question", "help", "anyone", "can i", "is there"],
}
TOPIC_KEYWORDS = {
    "state": ["state", "backend", "remote state", "state file"],
    "modules": ["module", "modules"],
    "providers": ["provider", "providers", "aws", "azurerm", "google"],
    "plans": ["plan", "apply", "destroy"],
    "workspaces": ["workspace", "workspaces"],
}


def load_json(input_path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def save_json(payload: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _first_sentence(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return fallback
    for separator in ".!?":
        if separator in cleaned:
            sentence = cleaned.split(separator, 1)[0].strip()
            if sentence:
                return sentence
    return cleaned[:180].strip()


def _call_llm(system_prompt: str, user_prompt: str) -> str | None:
    if not LLM_API_KEY:
        return None

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }
    request = Request(
        LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + LLM_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except URLError:
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    return choices[0].get("message", {}).get("content", "").strip() or None


def classify_post(title: str, body: str) -> str:
    prompt = load_prompt("classification.txt")
    llm_result = _call_llm(prompt, f"Title: {title}\n\nBody: {body}\n\nAnswer with one label only.")
    if llm_result:
        lowered = llm_result.lower()
        for category in CATEGORY_KEYWORDS:
            if category in lowered:
                return category
    text = f"{title} {body}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "question"


def summarize_post(title: str, body: str) -> str:
    prompt = load_prompt("summarization.txt")
    llm_result = _call_llm(prompt, f"Title: {title}\n\nBody: {body}")
    if llm_result:
        return llm_result
    return _first_sentence(body, title)


def detect_topic(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return topic
    return "general"


def process_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    for post in posts:
        title = post.get("title", "")
        body = post.get("body", "")
        processed.append(
            {
                **post,
                "classification": classify_post(title, body),
                "summary": summarize_post(title, body),
                "topic": detect_topic(title, body),
            }
        )
    return processed


def run(input_path: str | Path = "data/raw/reddit_posts.json", output_path: str | Path = "data/processed/processed_posts.json") -> Path:
    posts = load_json(input_path)
    processed = process_posts(posts)
    return save_json(processed, output_path)


if __name__ == "__main__":
    output = run()
    print(f"Saved processed posts to {output}")
