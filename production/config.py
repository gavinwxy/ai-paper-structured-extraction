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
