"""Batch extraction configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    input_dir: Path
    output_dir: Path
    # Input format. "md" (default) keeps the historical contract: discover *.md directly.
    # "json"/"jsonl" preprocess the parsed-block inputs into [§N]-marked Markdown first (written
    # to <output_dir>/_prepared_markdown), then discover from there. "auto" uses any *.md present
    # as-is, else converts whatever json/jsonl it finds. See production.runner.prepare_markdown_inputs.
    input_format: str = "md"
    model: str = "qwen3.5-35b-a3b"
    base_url: str = "http://35.220.164.252:3888/v1"
    api_key: str = ""
    paper_concurrency: int = 10
    llm_concurrency: int = 30
    temperature: float = 0.0
    # The proxy models (the qwen3.5-35b-a3b default, deepseek-v4-pro) have a smaller output
    # ceiling than the Gemini proxy; 32K is the proven-safe section budget, validated
    # thinking-off on both.
    max_tokens: int = 32_768
    # Budget for the single-shot planning/aux calls (census, relation pass, metadata,
    # references). The census is required, so a truncated census fails the whole paper —
    # 24K gives headroom over the old 16K for node-dense or reference-heavy papers while
    # staying well under the proxy output ceiling. Tunable via --planning-max-tokens.
    planning_max_tokens: int = 24_576
    max_retries: int = 3
    limit: int = 0
    force: bool = False
    log_level: str = "INFO"
    # Audit-only (P2 verifier): cross-check transcribed score values against the verbatim source
    # tables and record a `score_fidelity` block in extraction_notes. No effect on extracted data.
    verify_scores: bool = True
    # Input hygiene (default ON): feed the body-fed stages (node census, relation pass, content
    # fills, and citation Pass 1) the paper with its bibliography (and everything after it) stripped.
    # Metadata, reference metadata, and assembly/marker-resolution still use the full paper (the
    # tail-only cut keeps every earlier [§N] marker number stable). Set True to feed the full paper
    # to body-fed stages (the pre-cut behavior) — the opt-out arm for A/B. See
    # section_pipeline.slice_body_content.
    keep_references_in_body: bool = False
    # P3 cost lever (default ON since the cold A/B win): the three content sections share a
    # byte-identical paper-inclusive prompt prefix but fire concurrently, so the automatic
    # prefix-cache is cold when they race and the paper is re-sent uncached up to 3x. When True,
    # the first (cheapest) section runs to completion first to warm that prefix, then the rest hit
    # the cache. A clean disjoint-cold A/B (24 papers) fired 12/12 — method 7%->44%, evidence
    # 6%->39% cached, -18.4K tok/paper (~6% of the eff-cost proxy); it never worsens cache and is
    # redundant (not harmful) when the proxy is already warm. Cost is one section of serial latency
    # per paper, so disable with --no-warm-content-cache for latency-priority runs.
    warm_content_cache: bool = True
