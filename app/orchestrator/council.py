"""Council orchestrator: chaining + optional fix loop."""

import logging
import time
import uuid
from app.agents.cartographer import Cartographer
from app.agents.inspector import Inspector
from app.agents.sentinel import Sentinel
from app.synthesizer.arbiter import Arbiter
from app.memory.working_memory import WorkingMemory
from app.models.schemas import ReviewRequest, ReviewResponse, Finding, Severity

logger = logging.getLogger("synod.council")
MAX_FIX_ITER = 2


class Council:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.cartographer = Cartographer(llm_client)
        self.inspector = Inspector(llm_client)
        self.sentinel = Sentinel(llm_client)
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

        return ReviewResponse(
            session_id=session_id,
            findings=final_findings,
            summary=summary,
            total_findings=len(final_findings),
            tokens_used=self.llm.tokens_used,
            time_seconds=round(elapsed, 2),
            errors=errors,
        )

    async def _fix_loop(self, findings: list[Finding], code: str) -> list[Finding]:
        from app.agents.smith import Smith
        smith = Smith(self.llm)

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

    def _build_summary(self, findings: list[Finding]) -> str:
        if not findings:
            return "No issues found."
        critical = sum(1 for f in findings if f.impact == Severity.CRITICAL)
        high = sum(1 for f in findings if f.impact == Severity.HIGH)
        return f"{len(findings)} findings ({critical} critical, {high} high)."
