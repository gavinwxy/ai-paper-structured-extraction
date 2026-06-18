"""Async LLM client with global concurrency control and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from openai import AsyncOpenAI

# TruncationError is shared with the sync path so both transports raise one type: a RuntimeError
# (not ValueError) the worker's parse-retry loops — which catch only (JSONDecodeError, ValueError) —
# do NOT re-retry. A same-budget retry of a truncation is futile at temperature 0, so it fails fast
# to the paper-level handler at ~1x cost instead of ~4x.
from section_pipeline import TruncationError, _supports_prompt_cache_kwargs, _thinking_off_extra_body

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
        # paper_id -> stage -> token counters; drained per-paper into status.json so each
        # paper's passes (census / relations / metadata / references / section:*) are
        # attributable. This is the only token/cost telemetry the pipeline emits.
        self._usage: dict[str, dict[str, dict[str, int]]] = {}

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "total_errors": self._error_count,
            "total_latency_s": round(self._total_latency, 2),
            "avg_latency_s": round(self._total_latency / max(self._call_count, 1), 2),
        }

    @staticmethod
    def _new_usage_entry() -> dict[str, Any]:
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "cached_prompt_tokens": 0, "truncated": False}

    def _record_usage(self, paper_id: str, stage: str, usage: Any) -> None:
        """Accumulate one call's token usage under (paper_id, stage).

        Recorded right after the response returns — including truncated
        (finish_reason=length) attempts, whose tokens are still billed — so the per-pass
        totals reflect real cost, not just successful calls. A no-op when the provider
        omits `usage` (e.g. a proxy that doesn't surface it); the zeros are themselves a
        signal that usage isn't being reported.
        """
        if usage is None:
            return

        def _int(name: str) -> int:
            val = getattr(usage, name, 0)
            return int(val) if isinstance(val, (int, float)) else 0

        details = getattr(usage, "prompt_tokens_details", None)
        if isinstance(details, dict):
            cached = details.get("cached_tokens", 0)
        elif details is not None:
            cached = getattr(details, "cached_tokens", 0)
        else:
            cached = 0
        cached = int(cached) if isinstance(cached, (int, float)) else 0

        entry = self._usage.setdefault(paper_id, {}).setdefault(
            stage, self._new_usage_entry()
        )
        entry["calls"] += 1
        entry["prompt_tokens"] += _int("prompt_tokens")
        entry["completion_tokens"] += _int("completion_tokens")
        entry["total_tokens"] += _int("total_tokens")
        entry["cached_prompt_tokens"] += cached

    def _mark_truncated(self, paper_id: str, stage: str) -> None:
        """Flag the (paper_id, stage) usage entry as truncated (finish_reason=length).

        The entry usually already exists (recorded right before the truncation check), but
        setdefault keeps this safe if the provider omitted usage on the truncated attempt.
        """
        entry = self._usage.setdefault(paper_id, {}).setdefault(
            stage, self._new_usage_entry()
        )
        entry["truncated"] = True

    def drain_usage(self, paper_id: str) -> dict[str, Any]:
        """Pop this paper's accumulated usage as {by_stage, totals}.

        Per-paper (not global) so each status.json carries only its own passes; called
        once at the end of the paper's pipeline, on success and failure alike, which also
        keeps the accumulator from growing across a large batch.
        """
        by_stage = self._usage.pop(paper_id, {})
        numeric = ("calls", "prompt_tokens", "completion_tokens",
                   "total_tokens", "cached_prompt_tokens")
        totals: dict[str, Any] = {k: 0 for k in numeric}
        for entry in by_stage.values():
            for k in numeric:
                totals[k] += entry.get(k, 0)
        totals["truncated"] = any(bool(entry.get("truncated")) for entry in by_stage.values())
        return {"by_stage": by_stage, "totals": totals}

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
        # DeepSeek and Qwen reason by default; run extraction with thinking DISABLED (faster, no
        # quality lift on this corpus) via each family's own extra_body toggle. Models without
        # such a toggle are untouched.
        _thinking_extra = _thinking_off_extra_body(model)
        if _thinking_extra is not None:
            kwargs["extra_body"] = _thinking_extra
        # The explicit prompt-cache routing kwargs are OpenAI-proxy features; the official DeepSeek
        # API rejects unknown params (its caching is automatic). The worker already passes None for
        # deepseek — this guard keeps a future caller from 400-ing every call.
        if _supports_prompt_cache_kwargs(model):
            if prompt_cache_key:
                kwargs["prompt_cache_key"] = prompt_cache_key
            if prompt_cache_retention:
                kwargs["prompt_cache_retention"] = prompt_cache_retention

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            # The semaphore is the single global backpressure for the whole batch — it must be
            # held only for the API call itself. The backoff is captured here and slept after
            # the slot is released, so a wave of retrying tasks doesn't pin up to
            # max_concurrency slots in pure sleep and starve unrelated papers' calls.
            retry_delay = 0
            async with self._semaphore:
                t0 = time.monotonic()
                try:
                    response = await self._client.chat.completions.create(**kwargs)
                    elapsed = time.monotonic() - t0
                    self._record_usage(paper_id, stage, getattr(response, "usage", None))

                    choice = response.choices[0]
                    if choice.finish_reason == "length":
                        content = choice.message.content or ""
                        self._mark_truncated(paper_id, stage)
                        raise TruncationError(
                            f"LLM response truncated (finish_reason=length, got {len(content)} chars)"
                        )

                    self._call_count += 1
                    self._total_latency += elapsed
                    logger.debug(
                        "[%s] %s call OK (%.1fs, attempt %d)",
                        paper_id, stage, elapsed, attempt + 1,
                    )
                    return choice.message.content or ""

                except TruncationError:
                    # A same-budget retry of a truncation is futile at temperature 0 — fail fast
                    # (no sleep, no retry) so the paper-level handler marks it failed at ~1x cost.
                    # Stats-wise the call counts exactly once, as an error like any other failed
                    # attempt (`elapsed` was measured above, before the raise).
                    self._total_latency += elapsed
                    self._error_count += 1
                    logger.error(
                        "[%s] %s truncated (finish_reason=length) — failing fast, no retry",
                        paper_id, stage,
                    )
                    raise

                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    self._total_latency += elapsed
                    self._error_count += 1
                    last_error = exc

                    if attempt < self._max_retries:
                        retry_delay = min(2 ** attempt * 2, 30)
                        logger.warning(
                            "[%s] %s attempt %d failed (%.1fs): %s — retrying in %ds",
                            paper_id, stage, attempt + 1, elapsed, exc, retry_delay,
                        )
                    else:
                        logger.error(
                            "[%s] %s failed after %d attempts: %s",
                            paper_id, stage, self._max_retries + 1, exc,
                        )

            if retry_delay:
                await asyncio.sleep(retry_delay)

        raise RuntimeError(
            f"[{paper_id}] {stage} failed after {self._max_retries + 1} attempts"
        ) from last_error

    async def close(self) -> None:
        await self._client.close()
