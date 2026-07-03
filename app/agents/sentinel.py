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
- path/file operations using unsanitized/user-controlled input -> path traversal (CWE-22)
  Examples to flag:
    os.path.join("/safe/dir", user_input)            # path traversal via join
    open("/safe/dir/" + user_input)                  # path traversal via concat
    open(f"./static/{user_input}")                   # path traversal via f-string
    os.remove("/var/data/" + filename)               # path traversal in delete
- state-changing POST/PUT/DELETE routes with no CSRF token validation -> CWE-352
  Example to flag:
    @app.route("/transfer", methods=["POST"])        # POST route
    def transfer():                                  # mutates state
        amount = request.form["amount"]              # no CSRF check
- unescaped user input rendered into HTML/templates -> XSS (CWE-79)

If multiple instances of the same vulnerability class exist, report the most
severe or representative one and mention others exist in detail.

Only report findings you are confident about. If a pattern is ambiguous or
you are not certain it is exploitable, do not report it. Do not flag
architecture, coupling, or style issues — that is out of scope.

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

    async def validate_fix(self, finding: Finding, fix: str, original_code: str) -> bool:
        prompt = (
            f"Original finding: {finding.title}\n"
            f"CWE: {finding.cwe}\n"
            f"Detail: {finding.detail}\n\n"
            f"Proposed fix:\n```\n{fix}\n```\n\n"
            f"Does this fix resolve the vulnerability? Answer only 'yes' or 'no'."
        )
        response = await self.llm.complete(
            system="You are Sentinel, validating a proposed fix. Answer only yes or no.",
            user=prompt,
        )
        return response.strip().lower().startswith("yes")
