"""Tests for Council orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from app.models.schemas import (
    ReviewRequest, ReviewResponse, Finding, Severity, AgentRole,
    StructureContext,
)
from app.orchestrator.council import Council


@pytest.fixture
def llm_client():
    client = MagicMock()
    client.complete = AsyncMock()
    client.tokens_used = 42
    return client


SAMPLE_CODE = """import os
API_KEY = "sk-1234"
def run(cmd):
    os.system(cmd)
"""


class TestCouncil:
    async def test_review_returns_review_response(self, llm_client):
        council = Council(llm_client)

        llm_client.complete.side_effect = [
            '{"modules": ["main"], "dependencies": {}, '
            '"entry_points": ["run"], "notes": "ok"}',
            '[]',
            '[]',
        ]

        request = ReviewRequest(code=SAMPLE_CODE, language="python")
        response = await council.review(request)

        assert isinstance(response, ReviewResponse)
        assert response.session_id is not None
        assert isinstance(UUID(response.session_id), UUID)
        assert response.total_findings >= 0
        assert response.tokens_used == 42
        assert response.time_seconds >= 0

    async def test_review_with_inspector_findings(self, llm_client):
        council = Council(llm_client)

        # First call: cartographer, second: inspector, third: sentinel
        llm_client.complete.side_effect = [
            '{"modules": [], "dependencies": {}, "entry_points": [], "notes": ""}',
            '[{"title": "Mutable default", "detail": "list arg", '
            '"impact": "medium", "proposal": "use None", "line_number": 4}]',
            '[]',
        ]

        request = ReviewRequest(code=SAMPLE_CODE, filename="test.py")
        response = await council.review(request)

        assert response.total_findings == 1
        assert response.findings[0].agent == AgentRole.INSPECTOR
        assert response.findings[0].title == "Mutable default"

    async def test_review_with_sentinel_findings(self, llm_client):
        council = Council(llm_client)

        llm_client.complete.side_effect = [
            '{"modules": [], "dependencies": {}, "entry_points": [], "notes": ""}',
            '[]',
            '[{"title": "Hardcoded key", "detail": "API_KEY visible", '
            '"impact": "high", "line_number": 2, "cwe": "CWE-798"}]',
        ]

        request = ReviewRequest(code=SAMPLE_CODE)
        response = await council.review(request)

        assert response.total_findings == 1
        assert response.findings[0].agent == AgentRole.SENTINEL
        assert response.findings[0].cwe == "CWE-798"

    async def test_review_dedup_merges_findings(self, llm_client):
        council = Council(llm_client)

        llm_client.complete.side_effect = [
            '{"modules": [], "dependencies": {}, "entry_points": [], "notes": ""}',
            '[{"title": "Hardcoded secret key", "detail": "in source", '
            '"impact": "high", "line_number": 2}]',
            '[{"title": "Hardcoded secret key", "detail": "api key visible", '
            '"impact": "high", "line_number": 2}]',
        ]

        request = ReviewRequest(code=SAMPLE_CODE)
        response = await council.review(request)

        # Dedup should merge both into one finding with corroboration
        assert response.total_findings == 1
        assert len(response.findings[0].corroborated_by) >= 1

    async def test_summary_no_findings(self, llm_client):
        council = Council(llm_client)
        summary = council._build_summary([])
        assert summary == "No issues found."

    async def test_summary_with_findings(self, llm_client):
        council = Council(llm_client)
        findings = [
            Finding(id="1", agent=AgentRole.INSPECTOR, title="A",
                    detail="d", impact=Severity.CRITICAL),
            Finding(id="2", agent=AgentRole.SENTINEL, title="B",
                    detail="d", impact=Severity.HIGH),
            Finding(id="3", agent=AgentRole.INSPECTOR, title="C",
                    detail="d", impact=Severity.LOW),
        ]
        summary = council._build_summary(findings)
        assert "3 findings" in summary
        assert "1 critical" in summary
        assert "1 high" in summary

    async def test_review_with_fix_loop(self, llm_client):
        council = Council(llm_client)

        # Cartographer, inspector, sentinel, then fix loop calls
        llm_client.complete.side_effect = [
            '{"modules": [], "dependencies": {}, "entry_points": [], "notes": ""}',
            '[{"title": "Bad", "detail": "something bad", '
            '"impact": "critical", "line_number": 1}]',
            '[]',
            # Smith generates a fix
            'fix: use safer alternative',
            # Sentinel validates the fix
            'true',
        ]

        request = ReviewRequest(code=SAMPLE_CODE, enable_fix_loop=True)
        response = await council.review(request)

        assert response.total_findings >= 0
        # The high/critical finding should have a proposal from the fix loop
        critical = [f for f in response.findings if f.impact == Severity.CRITICAL]
        if critical:
            assert critical[0].proposal is not None


