"""Qwen Cloud API client (OpenAI-compatible endpoint)."""

from openai import AsyncOpenAI
from app.config import DASHSCOPE_API_KEY, QWEN_MODEL

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


class QwenClient:
    def __init__(self, api_key: str | None = None, model: str = QWEN_MODEL):
        self.client = AsyncOpenAI(
            api_key=api_key or DASHSCOPE_API_KEY,
            base_url=BASE_URL,
        )
        self.model = model
        self.tokens_used = 0

    async def complete(self, system: str, user: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self.tokens_used += response.usage.total_tokens
        return response.choices[0].message.content
