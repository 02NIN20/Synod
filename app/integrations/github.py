"""GitHub API helpers for PR comments and changed files."""

import logging
import httpx

logger = logging.getLogger("synod.github")
GITHUB_API_BASE = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def split_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, repo)."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Invalid repo format: {repo!r} (expected owner/repo)")
    return parts[0], parts[1]


async def post_pr_comment(repo: str, pr_number: int, body: str, token: str) -> bool:
    """Post a comment on a GitHub PR. Returns True on success."""
    owner, repo_name = split_repo(repo)
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/issues/{pr_number}/comments"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=_headers(token), json={"body": body})
        if response.status_code == 201:
            return True
        logger.error(
            "GitHub comment failed: %s %s - %s",
            response.status_code,
            response.reason_phrase,
            response.text,
        )
        return False
    except Exception as exc:  # pragma: no cover - network errors
        logger.exception("Failed to post GitHub PR comment: %s", exc)
        return False


async def get_pr_diff(repo: str, pr_number: int, token: str) -> list[dict]:
    """Fetch changed files in a PR. Returns list of dicts with filename and patch."""
    owner, repo_name = split_repo(repo)
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/pulls/{pr_number}/files"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=_headers(token))
        response.raise_for_status()
        files = response.json()
        return [
            {
                "filename": file.get("filename", ""),
                "patch": file.get("patch", ""),
                "status": file.get("status", ""),
                "additions": file.get("additions", 0),
                "deletions": file.get("deletions", 0),
            }
            for file in files
        ]
    except Exception as exc:  # pragma: no cover - network errors
        logger.exception("Failed to fetch PR diff: %s", exc)
        return []
