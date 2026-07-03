"""Cartographer agent: maps structure and dependencies."""

import json
from app.agents.base import BaseAgent
from app.models.schemas import Finding, AgentRole, Severity, StructureContext

SYSTEM_PROMPT = """You are Cartographer, a code structure analysis agent.
Map modules, dependencies, and entry points. Do not judge quality or security.
Output strict JSON matching StructureContext schema:
{"modules": [...], "dependencies": {...}, "entry_points": [...], "notes": "..."}
"""


class Cartographer(BaseAgent):
    role = AgentRole.CARTOGRAPHER

    async def map_structure(self, code: str, filename: str | None = None) -> StructureContext:
        prompt = self._build_prompt(code, None)
        response = await self.llm.complete(system=SYSTEM_PROMPT, user=prompt)
        try:
            data = json.loads(response)
            return StructureContext(**data)
        except (json.JSONDecodeError, TypeError):
            return StructureContext(notes="parse failed, empty context")

    async def analyze(self, code, filename=None, context=None) -> list[Finding]:
        # Cartographer does not emit findings, only structure context.
        return []
