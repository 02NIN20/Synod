"""Tests for Synod agents and arbiter."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.models.schemas import (
    Finding, Severity, AgentRole, StructureContext,
)
from app.agents.cartographer import Cartographer
from app.agents.inspector import Inspector
from app.agents.sentinel import Sentinel
from app.synthesizer.arbiter import Arbiter


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


class TestCartographer:
    async def test_map_structure_returns_context(self, llm_client):
        llm_client.complete.return_value = (
            '{"modules": ["main"], "dependencies": {"main": ["os"]}, '
            '"entry_points": ["run"], "notes": "simple script"}'
        )
        cart = Cartographer(llm_client)
        ctx = await cart.map_structure(SAMPLE_CODE, "test.py")
        assert isinstance(ctx, StructureContext)
        assert ctx.modules == ["main"]
        assert ctx.entry_points == ["run"]
        assert ctx.notes == "simple script"

    async def test_map_structure_handles_bad_json(self, llm_client):
        llm_client.complete.return_value = "not json"
        cart = Cartographer(llm_client)
        ctx = await cart.map_structure(SAMPLE_CODE)
        assert isinstance(ctx, StructureContext)
        assert ctx.notes == "parse failed, empty context"

    async def test_analyze_returns_empty(self, llm_client):
        cart = Cartographer(llm_client)
        findings = await cart.analyze(SAMPLE_CODE)
        assert findings == []


class TestInspector:
    async def test_analyze_returns_findings(self, llm_client):
        llm_client.complete.return_value = (
            '[{"title": "Mutable default arg", "detail": "list used as default", '
            '"impact": "medium", "proposal": "use None", "line_number": 5}]'
        )
        ins = Inspector(llm_client)
        findings = await ins.analyze(SAMPLE_CODE)
        assert len(findings) == 1
        assert findings[0].title == "Mutable default arg"
        assert findings[0].agent == AgentRole.INSPECTOR
        assert findings[0].impact == Severity.MEDIUM
        assert findings[0].proposal == "use None"
        assert findings[0].line_number == 5

    async def test_analyze_handles_bad_json(self, llm_client):
        llm_client.complete.return_value = "garbage"
        ins = Inspector(llm_client)
        findings = await ins.analyze(SAMPLE_CODE)
        assert findings == []

    async def test_analyze_limits_to_3(self, llm_client):
        llm_client.complete.return_value = (
            '[{"title": "A", "detail": "d", "impact": "low"}, '
            '{"title": "B", "detail": "d", "impact": "low"}, '
            '{"title": "C", "detail": "d", "impact": "low"}, '
            '{"title": "D", "detail": "d", "impact": "low"}]'
        )
        ins = Inspector(llm_client)
        findings = await ins.analyze(SAMPLE_CODE)
        assert len(findings) == 3

    async def test_analyze_skips_malformed_items(self, llm_client):
        llm_client.complete.return_value = (
            '[{"title": "Valid", "detail": "ok", "impact": "low"}, '
            '{"detail": "missing title", "impact": "low"}]'
        )
        ins = Inspector(llm_client)
        findings = await ins.analyze(SAMPLE_CODE)
        assert len(findings) == 1
        assert findings[0].title == "Valid"


class TestSentinel:
    async def test_analyze_returns_findings_with_cwe(self, llm_client):
        llm_client.complete.return_value = (
            '[{"title": "Hardcoded secret", "detail": "API_KEY exposed", '
            '"impact": "high", "line_number": 2, "cwe": "CWE-798"}]'
        )
        sent = Sentinel(llm_client)
        findings = await sent.analyze(SAMPLE_CODE)
        assert len(findings) == 1
        assert findings[0].agent == AgentRole.SENTINEL
        assert findings[0].impact == Severity.HIGH
        assert findings[0].cwe == "CWE-798"
        assert findings[0].line_number == 2

    async def test_analyze_handles_bad_json(self, llm_client):
        llm_client.complete.return_value = "bad"
        sent = Sentinel(llm_client)
        findings = await sent.analyze(SAMPLE_CODE)
        assert findings == []


class TestArbiter:
    def test_dedup_combines_similar(self):
        arb = Arbiter(AsyncMock())
        f1 = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                     title="Hardcoded secret key", detail="key in source",
                     impact=Severity.HIGH)
        f2 = Finding(id=str(uuid4()), agent=AgentRole.SENTINEL,
                     title="Hardcoded secret key", detail="api key visible",
                     impact=Severity.HIGH)
        deduped = arb._dedup([f1, f2])
        assert len(deduped) == 1
        assert AgentRole.SENTINEL in deduped[0].corroborated_by

    def test_dedup_preserves_different(self):
        arb = Arbiter(AsyncMock())
        f1 = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                     title="Bad naming", detail="foo",
                     impact=Severity.LOW)
        f2 = Finding(id=str(uuid4()), agent=AgentRole.SENTINEL,
                     title="SQL injection", detail="bar",
                     impact=Severity.CRITICAL)
        deduped = arb._dedup([f1, f2])
        assert len(deduped) == 2

    def test_validate_evidence_drops_bad_line(self):
        arb = Arbiter(AsyncMock())
        finding = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                          title="X", detail="d", impact=Severity.LOW,
                          line_number=999)
        code = "line1\nline2\n"
        valid = arb._validate_evidence([finding], code)
        assert len(valid) == 0

    def test_validate_evidence_keeps_good_line(self):
        arb = Arbiter(AsyncMock())
        finding = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                          title="X", detail="d", impact=Severity.LOW,
                          line_number=2)
        code = "line1\nline2\n"
        valid = arb._validate_evidence([finding], code)
        assert len(valid) == 1

    def test_validate_evidence_keeps_none_line(self):
        arb = Arbiter(AsyncMock())
        finding = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                          title="X", detail="d", impact=Severity.LOW)
        code = "line1\n"
        valid = arb._validate_evidence([finding], code)
        assert len(valid) == 1

    def test_apply_consensus_escalates_with_corroboration(self):
        arb = Arbiter(AsyncMock())
        finding = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                          title="X", detail="d", impact=Severity.LOW,
                          corroborated_by=[AgentRole.SENTINEL])
        result = arb._apply_consensus([finding])
        assert result[0].impact == Severity.MEDIUM
        assert result[0].confidence == 1.0

    def test_apply_consensus_no_corroboration(self):
        arb = Arbiter(AsyncMock())
        finding = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                          title="X", detail="d", impact=Severity.HIGH)
        result = arb._apply_consensus([finding])
        assert result[0].impact == Severity.HIGH
        assert result[0].confidence == 1.0

    async def test_synthesize_full_pipeline(self):
        arb = Arbiter(AsyncMock())
        f1 = Finding(id=str(uuid4()), agent=AgentRole.INSPECTOR,
                     title="Hardcoded secret", detail="key in source",
                     impact=Severity.HIGH, line_number=2)
        f2 = Finding(id=str(uuid4()), agent=AgentRole.SENTINEL,
                     title="Hardcoded secret", detail="secret exposed",
                     impact=Severity.HIGH, line_number=999)  # bad line
        code = "line1\nline2\n"
        result = arb.synthesize([f1, f2], code)
        # f2 dropped (bad line), f1 kept and gets corroboration boost
        assert len(result) == 1
        assert AgentRole.SENTINEL in result[0].corroborated_by
