"""API routes."""

import re
import time
from fastapi import APIRouter, Depends
from app.models.schemas import ReviewRequest, ReviewResponse, ChatRequest, ChatResponse
from app.orchestrator.council import Council
from app.llm.qwen_client import QwenClient

router = APIRouter(prefix="/api/v1")

CHAT_SYSTEM_PROMPT = (
    "You are Synod, a helpful coding assistant. "
    "Answer concisely and accurately. When asked about code, provide clear explanations."
)


def get_council() -> Council:
    return Council(QwenClient())


def _looks_like_code(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"```\w*", stripped):
        return True
    lines = [l for l in stripped.split("\n") if l.strip()]
    strong_start = ("def ", "class ", "import ", "from ", "async def", "@")
    for l in lines:
        if any(l.startswith(s) for s in strong_start):
            return True
        if re.search(r'\bdef\s+\w+\s*\(', l) or re.search(r'\bclass\s+\w+\s*:', l):
            return True
    code_keywords = {"def ", "class ", "import ", "from ", "return ", "if ", "for ", "while "}
    code_lines = sum(1 for l in lines if any(kw in l for kw in code_keywords))
    if len(lines) > 3 and code_lines >= 3:
        return True
    return False


def _summarize_findings(response: ReviewResponse) -> str:
    if not response.findings:
        return "No issues found in the code."

    parts = [f"Review complete — {response.summary}\n"]
    for i, f in enumerate(response.findings, 1):
        cwe = f" ({f.cwe})" if f.cwe else ""
        sev = f.impact.value.upper()
        parts.append(f"{i}. [{sev}{cwe}] {f.title} — {f.detail[:200]}")
    parts.append(f"\nTokens used: {response.tokens_used}")
    return "\n\n".join(parts)


@router.post("/review", response_model=ReviewResponse)
async def review(request: ReviewRequest, council: Council = Depends(get_council)):
    return await council.review(request)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start = time.time()

    if _looks_like_code(request.message):
        council = Council(QwenClient())
        review_req = ReviewRequest(code=request.message, filename="chat_pasted.py")
        try:
            result = await council.review(review_req)
            reply = _summarize_findings(result)
            elapsed = time.time() - start
            return ChatResponse(
                reply=reply,
                mode="council",
                tokens_used=result.tokens_used,
                time_seconds=round(elapsed, 2),
                findings_count=result.total_findings,
            )
        except Exception as e:
            reply = f"Council review failed: {e}"
    else:
        client = QwenClient()
        try:
            reply = await client.complete_with_history(
                system=CHAT_SYSTEM_PROMPT, history=request.history, user=request.message
            )
            elapsed = time.time() - start
            return ChatResponse(
                reply=reply,
                mode="direct",
                tokens_used=client.tokens_used,
                time_seconds=round(elapsed, 2),
            )
        except Exception as e:
            reply = f"LLM chat failed: {e}"

    elapsed = time.time() - start
    return ChatResponse(reply=reply, mode="error", time_seconds=round(elapsed, 2))
