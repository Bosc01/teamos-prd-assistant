"""Fetch open GitHub issues for selected repositories."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv

DEFAULT_REPOS = ["hashicorp/terraform", "hashicorp/terraform-provider-aws"]
DEFAULT_REPO_SLUGS = {
    "hashicorp/terraform": "terraform",
    "hashicorp/terraform-provider-aws": "terraform_aws",
}

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
API_URL_TEMPLATE = "https://api.github.com/repos/{repo}/issues"

# 100 pages x 100 per page = 10,000 issues per repo, far above any repo we crawl.
MAX_PAGES = 100
MAX_RETRIES = 5
MAX_RATE_LIMIT_WAIT_SECONDS = 300.0


def resolve_repos(repos: List[str] | None = None) -> List[str]:
    if repos:
        parsed = [repo.strip() for repo in repos if repo and repo.strip()]
        return parsed or list(DEFAULT_REPOS)

    raw = os.getenv("ISSUE_REPOS", "").strip()
    if not raw:
        return list(DEFAULT_REPOS)

    parsed = [repo.strip() for repo in raw.split(",") if repo.strip()]
    return parsed or list(DEFAULT_REPOS)


def repo_output_filename(repo: str) -> str:
    slug = DEFAULT_REPO_SLUGS.get(repo)
    if slug is None:
        slug = repo.lower().replace("/", "_").replace("-", "_")
    return f"{slug}_issues.json"


def _require_token() -> str:
    load_dotenv(ROOT / ".env")
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN. Add it to .env before running the pipeline.")
    return token


def _retry_delay_seconds(response, attempt: int) -> float:
    """Pick a backoff delay from GitHub's rate-limit headers, falling back to exponential."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass

    if response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset")
        try:
            wait = float(reset) - time.time()
        except (TypeError, ValueError):
            wait = 0.0
        if wait > 0:
            return min(wait + 1.0, MAX_RATE_LIMIT_WAIT_SECONDS)

    return min(float(2 ** attempt), 60.0)


def _get_with_retry(url: str, headers: Dict, params: Dict):
    """GET with bounded retries on 403/429 rate-limit responses."""
    response = None
    for attempt in range(MAX_RETRIES):
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code not in (403, 429):
            response.raise_for_status()
            return response
        if attempt < MAX_RETRIES - 1:
            delay = _retry_delay_seconds(response, attempt)
            print(f"Rate limited (HTTP {response.status_code}); retrying in {delay:.0f}s...")
            time.sleep(delay)
    response.raise_for_status()
    return response


def _fetch_repo_issues(
    repo: str,
    token: str,
    on_progress: Optional[Callable[[List[Dict]], None]] = None,
) -> List[Dict]:
    headers = {
        "Authorization": "token " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_issues: List[Dict] = []
    seen_numbers: set = set()

    for page in range(1, MAX_PAGES + 1):
        response = _get_with_retry(
            API_URL_TEMPLATE.format(repo=repo),
            headers=headers,
            # created/asc keeps page boundaries stable while issues are opened mid-crawl;
            # GitHub's default created/desc shifts every page as new issues arrive.
            params={
                "state": "open",
                "per_page": 100,
                "page": page,
                "sort": "created",
                "direction": "asc",
            },
        )

        page_data = response.json()
        if not page_data:
            break

        issues_only = [item for item in page_data if "pull_request" not in item]
        fresh = [item for item in issues_only if item.get("number") not in seen_numbers]
        seen_numbers.update(item.get("number") for item in fresh)
        all_issues.extend(fresh)

        if on_progress is not None:
            on_progress(all_issues)

        print(f"Fetched {len(page_data)} items from {repo} (page {page}); kept {len(fresh)} issues...")
    else:
        print(f"Stopping at page cap ({MAX_PAGES}) for {repo}; results may be truncated.")

    return all_issues


def _save_raw(filename: str, issues: List[Dict]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / filename
    out_path.write_text(json.dumps(issues, indent=2), encoding="utf-8")


def fetch_all_issues(repos: List[str] | None = None) -> None:
    token = _require_token()
    selected_repos = resolve_repos(repos)

    for repo in selected_repos:
        filename = repo_output_filename(repo)
        try:
            # Persist after every page so a mid-crawl failure keeps what was fetched.
            issues = _fetch_repo_issues(
                repo,
                token,
                on_progress=lambda fetched, filename=filename: _save_raw(filename, fetched),
            )
        except Exception:
            print(f"Fetch failed for {repo}; pages fetched so far are saved in data/raw/{filename}")
            raise
        _save_raw(filename, issues)
        print(f"Saved {len(issues)} issues to data/raw/{filename}")


if __name__ == "__main__":
    fetch_all_issues()
