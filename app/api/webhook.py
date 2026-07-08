"""GitHub pull_request webhook handler."""

import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import (
    GITHUB_MAX_FILE_LINES,
    GITHUB_MAX_FILES_PER_PR,
    GITHUB_TOKEN,
    GITHUB_WEBHOOK_SECRET,
)
from app.integrations.github import get_pr_diff, post_pr_comment
from app.llm.qwen_client import QwenClient
from app.models.schemas import Finding, ReviewRequest, ReviewResponse, Severity
from app.orchestrator.council import Council

logger = logging.getLogger("synod.webhook")
router = APIRouter(prefix="/api/v1/webhook")

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
    ".tf",
    ".sql",
}

SKIP_STATUSES = {"removed", "renamed"}
GITHUB_COMMENT_MAX_CHARS = 65000


def _is_code_file(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in CODE_EXTENSIONS)


def _verify_signature(payload: bytes, signature: Optional[str]) -> None:
    """Validate GitHub webhook HMAC-SHA256 signature."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured; rejecting webhook")
        raise HTTPException(status_code=403, detail="Webhook secret not configured")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature format")

    expected = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    provided = signature[7:]

    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _format_comment(files_findings: list[tuple[str, ReviewResponse]]) -> str:
    """Build a Markdown PR comment from per-file review responses."""
    total_findings = sum(r.total_findings for _, r in files_findings)
    total_tokens = sum(r.tokens_used for _, r in files_findings)

    lines: list[str] = [
        "## Synod Code Review",
        "",
        f"**Total findings:** {total_findings} | **Tokens used:** {total_tokens}",
        "",
    ]

    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]

    for filename, response in files_findings:
        if not response.findings:
            lines.append(f"<details>\n<summary>✅ {filename} — no issues</summary>\n\nNo findings.\n</details>\n")
            continue

        grouped: dict[Severity, list[Finding]] = {sev: [] for sev in severity_order}
        for finding in response.findings:
            grouped.setdefault(finding.impact, []).append(finding)

        file_lines: list[str] = []
        for sev in severity_order:
            findings = grouped.get(sev, [])
            if not findings:
                continue
            file_lines.append(f"### {sev.value.upper()}")
            for finding in findings:
                cwe = f" `{finding.cwe}`" if finding.cwe else ""
                line_info = f" (line {finding.line_number})" if finding.line_number else ""
                file_lines.append(
                    f"- **{finding.title}**{cwe}{line_info}\n"
                    f"  {finding.detail[:300]}{'...' if len(finding.detail) > 300 else ''}"
                )

        lines.append(
            f"<details>\n<summary>📝 {filename} — {response.total_findings} finding(s)</summary>\n\n"
            + "\n\n".join(file_lines)
            + "\n</details>\n"
        )

    return "\n".join(lines)


def _skip_comment(filename: str, reason: str) -> str:
    return f"- `{filename}`: {reason}"


async def _process_pr(repo: str, pr_number: int) -> None:
    """Background task: review changed files and post a single PR comment."""
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not configured; cannot process PR %s#%s", repo, pr_number)
        return

    files = await get_pr_diff(repo, pr_number, GITHUB_TOKEN)
    if not files:
        logger.info("No changed files for %s#%s", repo, pr_number)
        return

    if len(files) > GITHUB_MAX_FILES_PER_PR:
        body = (
            "## Synod Code Review\n\n"
            f"This PR changes **{len(files)}** files, which exceeds the review limit of "
            f"**{GITHUB_MAX_FILES_PER_PR}**. To avoid runaway token usage, the review was skipped.\n\n"
            "Consider splitting the PR into smaller changes or raising the limit via "
            "`GITHUB_MAX_FILES_PER_PR`."
        )
        await post_pr_comment(repo, pr_number, body, GITHUB_TOKEN)
        return

    code_files = [
        f for f in files
        if _is_code_file(f["filename"]) and f["status"] not in SKIP_STATUSES
    ]
    skipped: list[str] = []

    # Use one Council instance for the PR to reuse model clients.
    council = Council(QwenClient())
    files_findings: list[tuple[str, ReviewResponse]] = []

    for file_info in code_files:
        filename = file_info["filename"]
        patch = file_info.get("patch", "")

        # Review the patch as the changed file content. This avoids an extra
        # API call and keeps the review focused on the diff.
        lines = patch.splitlines()
        if len(lines) > GITHUB_MAX_FILE_LINES:
            skipped.append(_skip_comment(filename, f"file exceeds {GITHUB_MAX_FILE_LINES} lines"))
            continue

        try:
            request = ReviewRequest(code=patch, filename=filename, language="python")
            response = await council.review(request)
            files_findings.append((filename, response))
        except Exception as exc:  # pragma: no cover - LLM errors logged, not surfaced
            logger.exception("Review failed for %s in %s#%s: %s", filename, repo, pr_number, exc)
            skipped.append(_skip_comment(filename, "review failed"))

    if files_findings:
        body_parts: list[str] = [_format_comment(files_findings)]
    else:
        body_parts = ["## Synod Code Review\n\nNo reviewable code files found in this PR."]

    if skipped:
        body_parts.extend(["", "### Skipped files", ""] + skipped)

    body = "\n".join(body_parts)
    if len(body) > GITHUB_COMMENT_MAX_CHARS:
        body = body[:GITHUB_COMMENT_MAX_CHARS - 200]
        body += (
            "\n\n---\n"
            "⚠️ Comment truncated because it exceeded GitHub's maximum comment length. "
            "Consider reducing the number of changed files or the review scope."
        )

    await post_pr_comment(repo, pr_number, body, GITHUB_TOKEN)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """Receive GitHub pull_request webhooks and enqueue background review."""
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event {x_github_event!r} not handled"}

    try:
        data = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc

    action = data.get("action", "")
    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "reason": f"action {action!r} not handled"}

    pr = data.get("pull_request", {})
    pr_number = pr.get("number")
    repo_full_name = data.get("repository", {}).get("full_name")

    if not pr_number or not repo_full_name:
        raise HTTPException(status_code=400, detail="Missing PR number or repository")

    background_tasks.add_task(_process_pr, repo_full_name, pr_number)
    return {"status": "accepted", "repo": repo_full_name, "pr": pr_number}
