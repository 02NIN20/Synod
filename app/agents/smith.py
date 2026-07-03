"""Smith agent: generates fixes for high-severity findings."""

from app.models.schemas import Finding

SYSTEM_PROMPT = """You are Smith, a code fix agent.
Given a finding and the original code, generate a concrete fix.
Output only the fixed code snippet, no explanation, no markdown fences.
Keep the fix minimal and focused on the specific finding.
"""


class Smith:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def generate_fix(self, finding: Finding, code: str) -> str:
        prompt = (
            f"Finding: {finding.title}\n"
            f"Detail: {finding.detail}\n"
            f"Line: {finding.line_number}\n\n"
            f"Original code:\n```\n{code}\n```\n\n"
            f"Generate the fixed version of the relevant code section."
        )
        return await self.llm.complete(system=SYSTEM_PROMPT, user=prompt)
