"""Tests for API routes: FastAPI TestClient + _looks_like_code."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import _looks_like_code
from app.models.schemas import ReviewResponse, ChatResponse


# ---- _looks_like_code unit tests ----


@pytest.mark.parametrize(
    "text, expected",
    [
        ("def foo(): pass", True),
        ("class Foo:", True),
        ("import os", True),
        ("from os import path", True),
        ("async def handler(): pass", True),
        ("@app.get('/')", True),
        ("```python\nx=1\n```", True),
        ("```\nx=1\n```", True),
        ("", False),
        ("   ", False),
        ("Hello world", False),
        ("What is a lambda?", False),
        ("I have a class called Foo", False),
        ("x = 1", False),
        ("for i in range(10): pass", False),
        ("def\nfoo", False),
            ("a\nb\nc\nreturn x", False),
            ("if True:\n    pass\nelse:\n    pass\nx = 1", False),
    ],
)
def test_looks_like_code(text, expected):
    assert _looks_like_code(text) == expected


# ---- API endpoint tests ----


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_council():
    with patch("app.api.routes.Council") as MockCouncil:
        instance = MockCouncil.return_value
        instance.review = AsyncMock(return_value=ReviewResponse(
            session_id="test-session-1",
            summary="2 issues found",
            total_findings=2,
            tokens_used=100,
            time_seconds=0.5,
            findings=[],
        ))
        yield instance


@pytest.fixture
def mock_llm():
    with patch("app.api.routes.QwenClient") as MockClient:
        instance = MockClient.return_value
        instance.complete_with_history = AsyncMock(return_value="Hello from LLM")
        instance.tokens_used = 50
        yield instance


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_review_endpoint(client, mock_council):
    resp = client.post("/api/v1/review", json={
        "code": "def foo(): pass",
        "filename": "test.py",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "2 issues found"
    assert data["total_findings"] == 2
    assert data["tokens_used"] == 100


def test_review_invalid_payload(client):
    resp = client.post("/api/v1/review", json={"filename": "test.py"})
    assert resp.status_code == 422


def test_chat_code_route(client, mock_council):
    resp = client.post("/api/v1/chat", json={
        "message": "def foo(): pass",
        "history": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "council"
    assert data["findings_count"] == 2


def test_chat_text_route(client, mock_llm):
    resp = client.post("/api/v1/chat", json={
        "message": "What is Python?",
        "history": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "direct"
    assert data["reply"] == "Hello from LLM"


def test_chat_empty_message(client, mock_llm):
    resp = client.post("/api/v1/chat", json={
        "message": "",
        "history": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "direct"
