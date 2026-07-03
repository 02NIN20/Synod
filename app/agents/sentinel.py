"""Sentinel agent: security analysis."""

import json
import uuid
from app.agents.base import BaseAgent
from app.models.schemas import Finding, AgentRole, Severity, StructureContext

SYSTEM_PROMPT = """You are Sentinel, a security agent.
Detect vulnerabilities: OWASP Top 10, CWE-mapped issues. Max 5 findings.

Explicitly check every occurrence of these patterns, do not skip any:
- os.system, os.popen, subprocess.* (with or without shell=True) -> command injection (CWE-78)
- eval, exec, pickle.loads, yaml.load without SafeLoader -> code injection (CWE-94/502)
- string formatting/concatenation in SQL queries -> SQL injection (CWE-89)
- hardcoded credentials, API keys, tokens -> CWE-798
- path/file operations with unsanitized input -> path traversal (CWE-22)

If multiple instances of the same vulnerability class exist, report the most
severe or representative one and mention others exist in detail.

Output strict JSON list:
[{"title": "...", "detail": "...", "impact": "critical|high|medium|low",
  "proposal": "...", "line_number": N, "cwe": "CWE-XX"}]
"""


class Sentinel(BaseAgent):
    role = AgentRole.SENTINEL

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
                    cwe=item.get("cwe"),
                ))
            except (KeyError, ValueError):
                continue
        return findings

    async def validate_fix(self, finding: Finding, fix: str, code: str) -> bool:
        prompt = (
            f"Original issue: {finding.title}\n"
            f"Proposed fix:\n```\n{fix}\n```\n\n"
            f"Does this fix properly address the vulnerability? Answer only 'true' or 'false'."
        )
        response = await self.llm.complete(
            system="You are Sentinel validating a proposed fix. Return only 'true' or 'false'.",
            user=prompt,
        )
        return response.strip().lower() == "true"
