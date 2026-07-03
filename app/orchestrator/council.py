"""Council orchestrator: chaining + optional fix loop."""

import time
import uuid
from app.agents.cartographer import Cartographer
from app.agents.inspector import Inspector
from app.agents.sentinel import Sentinel
from app.synthesizer.arbiter import Arbiter
from app.memory.working_memory import WorkingMemory
from app.models.schemas import ReviewRequest, ReviewResponse, Finding, Severity

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
        self.memory.start_session(session_id)

        context = await self.cartographer.map_structure(request.code, request.filename)
        self.memory.set(session_id, "context", context)

        inspector_findings = await self.inspector.analyze(request.code, request.filename, context)
        sentinel_findings = await self.sentinel.analyze(request.code, request.filename, context)

        all_findings = inspector_findings + sentinel_findings

        if request.enable_fix_loop:
            all_findings = await self._fix_loop(all_findings, request.code)

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
        )

    async def _fix_loop(self, findings: list[Finding], code: str) -> list[Finding]:
        from app.agents.smith import Smith
        smith = Smith(self.llm)

        high_severity = [f for f in findings if f.impact in (Severity.HIGH, Severity.CRITICAL)]
        for finding in high_severity:
            for _ in range(MAX_FIX_ITER):
                fix = await smith.generate_fix(finding, code)
                approved = await self.sentinel.validate_fix(finding, fix, code)
                if approved:
                    finding.proposal = fix
                    break
        return findings

    def _build_summary(self, findings: list[Finding]) -> str:
        if not findings:
            return "No issues found."
        critical = sum(1 for f in findings if f.impact == Severity.CRITICAL)
        high = sum(1 for f in findings if f.impact == Severity.HIGH)
        return f"{len(findings)} findings ({critical} critical, {high} high)."
