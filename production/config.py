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
    # P3 cost lever (default ON since the cold A/B win): the three content sections share a
    # byte-identical paper-inclusive prompt prefix but fire concurrently, so the automatic
    # prefix-cache is cold when they race and the paper is re-sent uncached up to 3x. When True,
    # the first (cheapest) section runs to completion first to warm that prefix, then the rest hit
    # the cache. A clean disjoint-cold A/B (24 papers) fired 12/12 — method 7%->44%, evidence
    # 6%->39% cached, -18.4K tok/paper (~6% of the eff-cost proxy); it never worsens cache and is
    # redundant (not harmful) when the proxy is already warm. Cost is one section of serial latency
    # per paper, so disable with --no-warm-content-cache for latency-priority runs.
    warm_content_cache: bool = True
    # Blob-primary evidence (section-ir-0.12, default ON since the benchmark A/B win — mirror the
    # warm-cache rollout). When True the evidence pass uses the evidence-blob prompt module: the LLM
    # points at result tables by [§N] marker and transcribes only the contribution method's own score
    # rows (baselines + full ablation grids stay in the code-sliced verbatim table blob), mounts
    # findings on tables via Measure.finding_ids instead of Finding<->Measure edges, and emits a
    # headline_result one-liner. A 20-paper A/B fired 20/20 valid with 0 loss (headline_result + blob
    # cover the empty-main "contribution-as-modification" tables) at -12.9% cost (evidence completion
    # halved). Gates: evidence prompt module selection, the assembly Finding<->Measure edge-drop, and
    # the renderer blob path. Disable with --no-blob-primary-evidence for the section-ir-0.11 behavior.
    blob_primary_evidence: bool = True
    # Blob-primary references (section-ir-0.12, default OFF during rollout — mirror the blob-evidence
    # rollout: validate on the benchmark, then flip ON). References is now the #1 single-stage cost
    # ($0.132/20-paper benchmark, ~98% completion), of which ~58% is verbatim re-transcription of the
    # bibliography and ~60% of refs are background with a near-empty relation. When True the references
    # pass uses the references-extraction-blob prompt: the LLM transcribes a structured entry ONLY for
    # graph-linked references (a structural role builds_on/uses/compares_to or a non-empty provides_name)
    # and leaves background refs in the code-sliced verbatim bibliography blob (extraction_notes.
    # references_blob). reconcile_reference_units is unchanged (it only needs the linked subset). Gates:
    # references prompt selection (worker), the assembly blob slice, and the renderer full-bibliography
    # path. Disable with --no-blob-primary-references for the section-ir-0.11 full-transcription behavior.
    blob_primary_references: bool = False
