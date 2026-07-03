"""Arbiter: dedup, consensus, evidence validation, final synthesis."""

from difflib import SequenceMatcher
from app.models.schemas import Finding, Severity

SIMILARITY_THRESHOLD = 0.75


class Arbiter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def synthesize(self, findings: list[Finding], code: str) -> list[Finding]:
        deduped = self._dedup(findings)
        validated = self._validate_evidence(deduped, code)
        consensed = self._apply_consensus(validated)
        return consensed

    def _dedup(self, findings: list[Finding]) -> list[Finding]:
        result = []
        for f in findings:
            match = None
            for r in result:
                sim = SequenceMatcher(None, f.title.lower(), r.title.lower()).ratio()
                if sim > SIMILARITY_THRESHOLD:
                    match = r
                    break
            if match:
                if f.agent not in match.corroborated_by:
                    match.corroborated_by.append(f.agent)
            else:
                result.append(f)
        return result

    def _validate_evidence(self, findings: list[Finding], code: str) -> list[Finding]:
        lines = code.splitlines()
        valid = []
        for f in findings:
            if f.line_number is None:
                valid.append(f)
                continue
            if 0 < f.line_number <= len(lines):
                valid.append(f)
            # else: drop, hallucinated line number
        return valid

    def _apply_consensus(self, findings: list[Finding]) -> list[Finding]:
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        for f in findings:
            if len(f.corroborated_by) >= 1:
                idx = severity_order.index(f.impact)
                f.impact = severity_order[min(idx + 1, len(severity_order) - 1)]
                f.confidence = min(1.0, f.confidence + 0.2 * len(f.corroborated_by))
        return findings
