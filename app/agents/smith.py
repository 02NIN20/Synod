"""Smith agent: generates fixes for findings."""

from app.agents.base import BaseAgent
from app.models.schemas import Finding, AgentRole


class Smith(BaseAgent):
    role = AgentRole.SMITH

    async def generate_fix(self, finding: Finding, code: str) -> str:
        prompt = (
            f"Given this finding:\n{finding.title}\n{finding.detail}\n\n"
            f"And this code:\n```\n{code}\n```\n\n"
            f"Generate a fix. Return ONLY the corrected code snippet."
        )
        response = await self.llm.complete(
            system="You are Smith, a fix generator. Output only the corrected code.",
            user=prompt,
        )
        return response

    async def analyze(self, code, filename=None, context=None):
        return []
