"""Tests for GitHub PR integration and webhook handler."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def webhook_secret():
    with patch("app.api.webhook.GITHUB_WEBHOOK_SECRET", "super-secret"):
        yield


@pytest.fixture
def github_token():
    with patch("app.api.webhook.GITHUB_TOKEN", "ghp_token"):
        yield


@pytest.fixture
def mock_council():
    mock = MagicMock()
    mock_review = AsyncMock()
    mock.return_value.review = mock_review
    with patch("app.api.webhook.Council", mock):
        yield mock, mock_review


def _build_pr_payload(action: str = "opened", number: int = 42, repo: str = "owner/repo") -> dict:
    return {
        "action": action,
        "number": number,
        "pull_request": {"number": number, "title": "Test PR"},
        "repository": {"full_name": repo},
    }


def test_webhook_rejects_missing_signature(client, webhook_secret):
    payload = json.dumps(_build_pr_payload()).encode()
    response = client.post(
        "/api/v1/webhook/github",
        content=payload,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing signature"


def test_webhook_rejects_invalid_signature(client, webhook_secret):
    payload = json.dumps(_build_pr_payload()).encode()
    response = client.post(
        "/api/v1/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"


def test_webhook_rejects_when_secret_not_configured(client):
    # webhook_secret fixture NOT applied here, so GITHUB_WEBHOOK_SECRET is patched to empty.
    payload = json.dumps(_build_pr_payload()).encode()
    response = client.post(
        "/api/v1/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": _signature(payload, "any"),
        },
    )
    assert response.status_code == 403


def test_webhook_accepts_valid_signature_and_enqueues_review(
    client, webhook_secret, github_token, mock_council
):
    _, mock_review = mock_council
    mock_review.return_value = MagicMock(
        findings=[],
        summary="No issues found.",
        total_findings=0,
        tokens_used=10,
        time_seconds=0.0,
        errors=[],
    )

    files_response = [
        {"filename": "main.py", "patch": "print('hello')", "status": "modified", "additions": 1}
    ]

    with patch("app.api.webhook.get_pr_diff", new=AsyncMock(return_value=files_response)) as mock_diff:
        with patch("app.api.webhook.post_pr_comment", new=AsyncMock(return_value=True)) as mock_post:
            payload = json.dumps(_build_pr_payload()).encode()
            response = client.post(
                "/api/v1/webhook/github",
                content=payload,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": _signature(payload, "super-secret"),
                },
            )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    mock_diff.assert_awaited_once_with("owner/repo", 42, "ghp_token")
    mock_review.assert_awaited_once()
    mock_post.assert_awaited_once()
    posted_body = mock_post.await_args.args[2]
    assert "## Synod Code Review" in posted_body


def test_webhook_ignores_non_pull_request_event(client, webhook_secret):
    payload = json.dumps({"action": "opened"}).encode()
    response = client.post(
        "/api/v1/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _signature(payload, "super-secret"),
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_ignores_unhandled_action(client, webhook_secret):
    payload = json.dumps(_build_pr_payload(action="closed")).encode()
    response = client.post(
        "/api/v1/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": _signature(payload, "super-secret"),
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_skips_when_file_count_exceeds_limit(
    client, webhook_secret, github_token, mock_council
):
    files_response = [
        {"filename": f"file{i}.py", "patch": "x = 1", "status": "modified", "additions": 1}
        for i in range(12)
    ]

    with patch("app.api.webhook.GITHUB_MAX_FILES_PER_PR", 10):
        with patch("app.api.webhook.get_pr_diff", new=AsyncMock(return_value=files_response)):
            with patch("app.api.webhook.post_pr_comment", new=AsyncMock(return_value=True)) as mock_post:
                payload = json.dumps(_build_pr_payload()).encode()
                response = client.post(
                    "/api/v1/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": _signature(payload, "super-secret"),
                    },
                )

    assert response.status_code == 200
    posted_body = mock_post.await_args.args[2]
    assert "exceeds the review limit" in posted_body
    assert "12" in posted_body


def test_format_comment_groups_by_severity():
    from app.api.webhook import _format_comment
    from app.models.schemas import Finding, ReviewResponse, Severity, AgentRole, FindingSource

    response = ReviewResponse(
        session_id="s1",
        findings=[
            Finding(
                id="f1",
                agent=AgentRole.SENTINEL,
                title="SQL injection",
                detail="Unsafe query construction",
                impact=Severity.HIGH,
                line_number=10,
                cwe="CWE-89",
                source=FindingSource.LLM,
            ),
            Finding(
                id="f2",
                agent=AgentRole.INSPECTOR,
                title="Unused import",
                detail="Import os is never used",
                impact=Severity.LOW,
                line_number=3,
                source=FindingSource.LLM,
            ),
        ],
        summary="2 findings",
        total_findings=2,
        tokens_used=100,
        time_seconds=1.0,
    )

    body = _format_comment([("app.py", response)])
    assert "## Synod Code Review" in body
    assert "**Total findings:** 2" in body
    assert "### HIGH" in body
    assert "### LOW" in body
    assert "`CWE-89`" in body
    assert "(line 10)" in body
    assert "<details>" in body
