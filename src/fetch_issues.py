"""Fetch open GitHub issues for selected HashiCorp repositories."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

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


def _fetch_repo_issues(repo: str, token: str) -> List[Dict]:
    headers = {
        "Authorization": "token " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_issues: List[Dict] = []
    page = 1

    while True:
        response = requests.get(
            API_URL_TEMPLATE.format(repo=repo),
            headers=headers,
            params={"state": "open", "per_page": 100, "page": page},
            timeout=30,
        )
        response.raise_for_status()

        page_data = response.json()
        if not page_data:
            break

        issues_only = [item for item in page_data if "pull_request" not in item]
        all_issues.extend(issues_only)

        print(f"Fetched {len(page_data)} items from {repo} (page {page}); kept {len(issues_only)} issues...")
        page += 1

    return all_issues


def _save_raw(filename: str, issues: List[Dict]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / filename
    out_path.write_text(json.dumps(issues, indent=2), encoding="utf-8")


def fetch_all_issues(repos: List[str] | None = None) -> None:
    token = _require_token()
    selected_repos = resolve_repos(repos)

    for repo in selected_repos:
        issues = _fetch_repo_issues(repo, token)
        filename = repo_output_filename(repo)
        _save_raw(filename, issues)
        print(f"Saved {len(issues)} issues to data/raw/{filename}")


if __name__ == "__main__":
    fetch_all_issues()
