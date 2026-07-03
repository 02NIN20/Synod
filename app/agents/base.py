"""BaseAgent for Synod."""

from abc import ABC, abstractmethod
from app.models.schemas import Finding, StructureContext


class BaseAgent(ABC):
    role: str

    def __init__(self, llm_client):
        self.llm = llm_client

    @abstractmethod
    async def analyze(
        self,
        code: str,
        filename: str | None = None,
        context: StructureContext | None = None,
    ) -> list[Finding]:
        """Analyze code, return findings. Max 3 per call."""
        ...

    def _build_prompt(self, code: str, context: StructureContext | None) -> str:
        base = f"Code to review:\n```\n{code}\n```\n"
        if context:
            base += f"\nStructure context:\n{context.model_dump_json()}\n"
        return base
