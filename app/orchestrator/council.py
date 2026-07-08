"""Council orchestrator: chaining + optional fix loop."""

import logging
import time
import uuid
from app.agents.cartographer import Cartographer
from app.agents.inspector import Inspector
from app.agents.sentinel import Sentinel
from app.synthesizer.arbiter import Arbiter
from app.memory.working_memory import WorkingMemory
from app.models.schemas import (
    ReviewRequest, ReviewResponse, Finding, Severity, SemgrepFinding, FindingSource,
)
from app.tools.semgrep_scanner import run_semgrep
from app.config import QWEN_AGENT_MODEL
from app.llm.qwen_client import QwenClient

logger = logging.getLogger("synod.council")
MAX_FIX_ITER = 2


class Council:
    def __init__(self, llm_client):
        self.llm = llm_client
        # Agents that require strict JSON output use a dedicated model
        # (e.g. qwen3-coder-plus or qwen3-coder-next) when the main model
        # does not reliably follow structured-output prompts.
        self.agent_llm = (
            llm_client
            if QWEN_AGENT_MODEL == llm_client.model
            else QwenClient(model=QWEN_AGENT_MODEL)
        )
        self.cartographer = Cartographer(self.agent_llm)
        self.inspector = Inspector(self.agent_llm)
        self.sentinel = Sentinel(self.agent_llm)
        self.arbiter = Arbiter(llm_client)
        self.memory = WorkingMemory()

    async def review(self, request: ReviewRequest) -> ReviewResponse:
        session_id = str(uuid.uuid4())
        start = time.time()
        errors: list[str] = []
        self.memory.start_session(session_id)

        try:
            context = await self.cartographer.map_structure(request.code, request.filename)
        except Exception as e:
            logger.warning("Cartographer failed: %s", e)
            errors.append(f"Cartographer: {e}")
            context = None

        # Semgrep pre-filter: runs after Cartographer, before Sentinel.
        # Graceful fallback to empty list if semgrep is unavailable.
        try:
            raw_semgrep = run_semgrep(request.code, request.filename or "snippet.py")
        except Exception as e:
            logger.warning("Semgrep pre-filter failed: %s", e)
            errors.append(f"Semgrep: {e}")
            raw_semgrep = []

        if context is None:
            from app.models.schemas import StructureContext
            context = StructureContext()
        context.semgrep_findings = [SemgrepFinding(**r) for r in raw_semgrep]
        self.memory.set(session_id, "context", context)

        inspector_findings = []
        sentinel_findings = []

        try:
            inspector_findings = await self.inspector.analyze(request.code, request.filename, context)
        except Exception as e:
            logger.warning("Inspector failed: %s", e)
            errors.append(f"Inspector: {e}")

        try:
            sentinel_findings = await self.sentinel.analyze(request.code, request.filename, context)
        except Exception as e:
            logger.warning("Sentinel failed: %s", e)
            errors.append(f"Sentinel: {e}")
            # Fallback: use semgrep findings directly if Sentinel's LLM fails
            sentinel_findings = self.sentinel.findings_from_semgrep(context)

        # Tag Sentinel findings that match semgrep candidates so source
        # tracking stays accurate without bypassing Sentinel's validation.
        sentinel_findings = self._tag_semgrep_sources(sentinel_findings, raw_semgrep)

        all_findings = inspector_findings + sentinel_findings

        if request.enable_fix_loop and all_findings:
            try:
                all_findings = await self._fix_loop(all_findings, request.code)
            except Exception as e:
                logger.warning("Fix loop failed: %s", e)
                errors.append(f"Fix loop: {e}")

        final_findings = self.arbiter.synthesize(all_findings, request.code)

        summary = self._build_summary(final_findings)
        elapsed = time.time() - start

        total_tokens = self.llm.tokens_used + self.agent_llm.tokens_used
        return ReviewResponse(
            session_id=session_id,
            findings=final_findings,
            summary=summary,
            total_findings=len(final_findings),
            tokens_used=total_tokens,
            time_seconds=round(elapsed, 2),
            errors=errors,
        )

    async def _fix_loop(self, findings: list[Finding], code: str) -> list[Finding]:
        from app.agents.smith import Smith
        smith = Smith(self.agent_llm)

        high_severity = [f for f in findings if f.impact in (Severity.HIGH, Severity.CRITICAL)]
        for finding in high_severity:
            approved = False
            last_fix = None
            for _ in range(MAX_FIX_ITER):
                try:
                    last_fix = await smith.generate_fix(finding, code)
                    approved = await self.sentinel.validate_fix(finding, last_fix, code)
                except Exception:
                    break
                if approved:
                    finding.proposal = last_fix
                    break
            if not approved:
                finding.proposal = (
                    f"[Auto-fix not confirmed after {MAX_FIX_ITER} attempts. "
                    f"Manual review required.]"
                )
        return findings

    def _tag_semgrep_sources(
        self, findings: list[Finding], raw_semgrep: list[dict]
    ) -> list[Finding]:
        """Mark LLM-validated findings as semgrep-sourced when they match."""
        for f in findings:
            if not f.cwe or f.line_number is None:
                continue
            for raw in raw_semgrep:
                raw_cwe = raw.get("cwe", "")
                if not raw_cwe:
                    from app.tools.semgrep_scanner import CWE_MAP
                    raw_cwe = CWE_MAP.get(raw.get("rule_id", ""), "")
                if raw_cwe == f.cwe and abs(f.line_number - raw.get("line", 0)) <= 2:
                    f.source = FindingSource.SEMGREP
                    f.confidence = max(f.confidence, 0.9)
                    break
        return findings

    def _build_summary(self, findings: list[Finding]) -> str:
        if not findings:
            return "No issues found."
        critical = sum(1 for f in findings if f.impact == Severity.CRITICAL)
        high = sum(1 for f in findings if f.impact == Severity.HIGH)
        return f"{len(findings)} findings ({critical} critical, {high} high)."
