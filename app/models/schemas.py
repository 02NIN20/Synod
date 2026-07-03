"""Pydantic models for Synod: requests, responses, findings."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentRole(str, Enum):
    CARTOGRAPHER = "cartographer"
    INSPECTOR = "inspector"
    SENTINEL = "sentinel"
    SMITH = "smith"


class Finding(BaseModel):
    id: str
    agent: AgentRole
    title: str = Field(..., description="One-line conclusion")
    detail: str = Field(..., description="Evidence: line numbers, snippet, CWE")
    impact: Severity
    proposal: Optional[str] = Field(None, description="Fix: BEFORE/AFTER")
    line_number: Optional[int] = None
    cwe: Optional[str] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    corroborated_by: list[AgentRole] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    code: str
    filename: Optional[str] = None
    language: str = "python"
    enable_fix_loop: bool = False


class ReviewResponse(BaseModel):
    session_id: str
    findings: list[Finding]
    summary: str
    total_findings: int
    tokens_used: int
    time_seconds: float
    errors: list[str] = Field(default_factory=list)


class StructureContext(BaseModel):
    """Output from Cartographer, passed to Inspector and Sentinel."""
    modules: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    entry_points: list[str] = Field(default_factory=list)
    notes: str = ""
