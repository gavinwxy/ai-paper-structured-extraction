"""Async LLM client with global concurrency control and retry logic."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI

from section_pipeline import _is_deepseek_model

logger = logging.getLogger(__name__)


class LLMClient:
    """Wraps AsyncOpenAI with a global semaphore for backpressure and retry logic."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_concurrency: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_retries = max_retries
        self._call_count = 0
        self._total_latency = 0.0
        self._error_count = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "total_errors": self._error_count,
            "total_latency_s": round(self._total_latency, 2),
            "avg_latency_s": round(self._total_latency / max(self._call_count, 1), 2),
        }

    async def call(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.0,
        max_tokens: int = 16_384,
        response_format: dict | None = None,
        prompt_cache_key: str | None = None,
        prompt_cache_retention: str | None = None,
        paper_id: str = "",
        stage: str = "",
    ) -> str:
        """Make an async LLM call with semaphore-based concurrency control and retries."""
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format is not None:
            kwargs["response_format"] = response_format
        # DeepSeek reasons by default; run extraction with thinking DISABLED (faster, no
        # quality lift on this corpus). Gated to deepseek so other models are untouched.
        if _is_deepseek_model(model):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key
        if prompt_cache_retention:
            kwargs["prompt_cache_retention"] = prompt_cache_retention

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            async with self._semaphore:
                t0 = time.monotonic()
                try:
                    response = await self._client.chat.completions.create(**kwargs)
                    elapsed = time.monotonic() - t0
                    self._call_count += 1
                    self._total_latency += elapsed

                    choice = response.choices[0]
                    if choice.finish_reason == "length":
                        content = choice.message.content or ""
                        raise ValueError(
                            f"LLM response truncated (finish_reason=length, got {len(content)} chars)"
                        )

                    logger.debug(
                        "[%s] %s call OK (%.1fs, attempt %d)",
                        paper_id, stage, elapsed, attempt + 1,
                    )
                    return choice.message.content or ""

                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    self._total_latency += elapsed
                    self._error_count += 1
                    last_error = exc

                    if attempt < self._max_retries:
                        delay = min(2 ** attempt * 2, 30)
                        logger.warning(
                            "[%s] %s attempt %d failed (%.1fs): %s — retrying in %ds",
                            paper_id, stage, attempt + 1, elapsed, exc, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "[%s] %s failed after %d attempts: %s",
                            paper_id, stage, self._max_retries + 1, exc,
                        )

        raise RuntimeError(
            f"[{paper_id}] {stage} failed after {self._max_retries + 1} attempts"
        ) from last_error

    async def close(self) -> None:
        await self._client.close()
