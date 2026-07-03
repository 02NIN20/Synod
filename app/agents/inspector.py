"""Inspector agent: code quality analysis."""

import json
import uuid
from app.agents.base import BaseAgent
from app.models.schemas import Finding, AgentRole, Severity, StructureContext

SYSTEM_PROMPT = """You are Inspector, a code quality agent.
Detect anti-patterns, complexity issues, maintainability problems.
Do not assess security. Max 5 findings.
Output strict JSON list:
[{"title": "...", "detail": "...", "impact": "critical|high|medium|low",
  "proposal": "...", "line_number": N}]
"""


class Inspector(BaseAgent):
    role = AgentRole.INSPECTOR

    async def analyze(
        self, code: str, filename: str | None = None, context: StructureContext | None = None
    ) -> list[Finding]:
        prompt = self._build_prompt(code, context)
        response = await self.llm.complete(system=SYSTEM_PROMPT, user=prompt)
        try:
            items = json.loads(response)
        except json.JSONDecodeError:
            return []

        findings = []
        for item in items[:5]:
            try:
                findings.append(Finding(
                    id=str(uuid.uuid4()),
                    agent=self.role,
                    title=item["title"],
                    detail=item["detail"],
                    impact=Severity(item["impact"]),
                    proposal=item.get("proposal"),
                    line_number=item.get("line_number"),
                ))
            except (KeyError, ValueError):
                continue
        return findings
