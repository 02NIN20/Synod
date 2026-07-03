"""API routes."""

from fastapi import APIRouter, Depends
from app.models.schemas import ReviewRequest, ReviewResponse
from app.orchestrator.council import Council
from app.llm.qwen_client import QwenClient

router = APIRouter(prefix="/api/v1")


def get_council() -> Council:
    return Council(QwenClient())


@router.post("/review", response_model=ReviewResponse)
async def review(request: ReviewRequest, council: Council = Depends(get_council)):
    return await council.review(request)
