"""Batch extraction configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    input_dir: Path
    output_dir: Path
    model: str = "deepseek-v4-pro"
    base_url: str = "http://35.220.164.252:3888/v1"
    api_key: str = ""
    paper_concurrency: int = 10
    llm_concurrency: int = 30
    temperature: float = 0.0
    # DeepSeek (the default) has a smaller output ceiling than the Gemini proxy; 32K is the
    # proven-safe section budget (a higher value 400s on deepseek-v4-pro).
    max_tokens: int = 32_768
    # Budget for the single-shot planning/aux calls (census, relation pass, metadata,
    # references). The census is required, so a truncated census fails the whole paper —
    # 24K gives headroom over the old 16K for node-dense or reference-heavy papers while
    # staying well under the deepseek ceiling. Tunable via --planning-max-tokens.
    planning_max_tokens: int = 24_576
    max_retries: int = 3
    limit: int = 0
    force: bool = False
    log_level: str = "INFO"
    # Audit-only (P2 verifier): cross-check transcribed score values against the verbatim source
    # tables and record a `score_fidelity` block in extraction_notes. No effect on extracted data.
    verify_scores: bool = True
    # P3 cost lever (opt-in, default off): the three content sections share a byte-identical
    # paper-inclusive prompt prefix but fire concurrently, so the automatic prefix-cache is cold
    # when they race and the paper is re-sent uncached up to 3x. When True, the first (cheapest)
    # section runs to completion first to warm that prefix, then the rest hit the cache. Measured
    # headroom ~6% of the eff-cost proxy on the 0.11 benchmark; costs one section of serial
    # latency. Validate per-proxy before enabling — automatic-cache warming is timing-dependent.
    warm_content_cache: bool = False
