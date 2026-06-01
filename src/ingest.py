from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

DEFAULT_QUERY = "terraform"
DEFAULT_LIMIT = 25
DEFAULT_OUTPUT_PATH = Path("data/raw/reddit_posts.json")
SAMPLE_INPUT_PATH = Path("data/raw/sample_reddit_posts.json")
REDDIT_SEARCH_URL = (
    "https://www.reddit.com/r/terraform/search.json?q={query}"
    "&restrict_sr=on&sort=new&limit={limit}"
)


def _normalize_posts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for child in payload.get("data", {}).get("children", []):
        data = child.get("data", {})
        posts.append(
            {
                "id": data.get("id"),
                "title": data.get("title", "").strip(),
                "body": data.get("selftext", "").strip(),
                "subreddit": data.get("subreddit"),
                "author": data.get("author"),
                "created_utc": data.get("created_utc"),
                "score": data.get("score"),
                "num_comments": data.get("num_comments"),
                "url": f"https://www.reddit.com{data.get('permalink', '')}",
            }
        )
    return posts


def fetch_reddit_posts(query: str = DEFAULT_QUERY, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Fetch Terraform-related Reddit posts from r/terraform."""
    url = REDDIT_SEARCH_URL.format(query=quote_plus(query), limit=limit)
    request = Request(url, headers={"User-Agent": "TeamOS-PRD-Assistant/1.0"})

    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    return _normalize_posts(payload)


def load_sample_posts(sample_path: str | Path = SAMPLE_INPUT_PATH) -> list[dict[str, Any]]:
    return json.loads(Path(sample_path).read_text(encoding="utf-8"))


def get_posts(query: str = DEFAULT_QUERY, limit: int = DEFAULT_LIMIT) -> tuple[list[dict[str, Any]], str]:
    try:
        return fetch_reddit_posts(query=query, limit=limit), "reddit"
    except URLError:
        return load_sample_posts(), "sample"


def save_posts(posts: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(posts, indent=2), encoding="utf-8")
    return path



def run(
    query: str = DEFAULT_QUERY,
    limit: int = DEFAULT_LIMIT,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> tuple[Path, str]:
    posts, source = get_posts(query=query, limit=limit)
    return save_posts(posts, output_path), source


if __name__ == "__main__":
    output, source = run()
    print(f"Saved raw Reddit posts to {output} (source: {source})")
