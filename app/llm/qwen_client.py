"""Qwen Cloud API client (OpenAI-compatible endpoint) with retry and timeout."""

import asyncio
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError
from app.config import DASHSCOPE_API_KEY, QWEN_MODEL

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MAX_RETRIES = 3
BASE_DELAY = 1.0
TIMEOUT_SECONDS = 30


class QwenClient:
    def __init__(self, api_key: str | None = None, model: str = QWEN_MODEL):
        self.client = AsyncOpenAI(
            api_key=api_key or DASHSCOPE_API_KEY,
            base_url=BASE_URL,
            timeout=TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.model = model
        self.tokens_used = 0

    async def complete(self, system: str, user: str) -> str:
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    ),
                    timeout=TIMEOUT_SECONDS,
                )
                self.tokens_used += response.usage.total_tokens
                return response.choices[0].message.content
            except RateLimitError as e:
                last_error = e
                delay = BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
            except (APITimeoutError, asyncio.TimeoutError):
                last_error = Exception("Request timed out")
                await asyncio.sleep(BASE_DELAY)
            except APIConnectionError as e:
                last_error = e
                await asyncio.sleep(BASE_DELAY * (2 ** attempt))

    async def complete_with_history(self, system: str, history: list[dict], user: str) -> str:
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user}]
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                    ),
                    timeout=TIMEOUT_SECONDS,
                )
                self.tokens_used += response.usage.total_tokens
                return response.choices[0].message.content
            except RateLimitError as e:
                last_error = e
                delay = BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
            except (APITimeoutError, asyncio.TimeoutError):
                last_error = Exception("Request timed out")
                await asyncio.sleep(BASE_DELAY)
            except APIConnectionError as e:
                last_error = e
                await asyncio.sleep(BASE_DELAY * (2 ** attempt))
        raise last_error or Exception("LLM call failed after retries")
