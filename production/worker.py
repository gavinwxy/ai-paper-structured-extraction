"""Per-paper async extraction pipeline (section-ir-0.12) with intermediate saves.

Three stages: node census (A) -> relation pass (B) -> per-section content fill (C),
then deterministic assembly and validation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from section_pipeline import (
    STAGE_B_RELATIONS_NOTE,
    enrich_metadata,
    load_prompt,
    load_node_census_schema,
    load_relation_pass_schema,
    load_section_schema,
    load_section_module,
    load_references_schema_for_mode,
    slice_metadata_input,
    strip_blob_evidence_schema,
    build_response_format,
    schema_to_prompt_spec,
    _augment_prompt_for_json_object,
    _structured_output_mode,
    _supports_prompt_cache_kwargs,
    normalize_census_nodes,
    validate_census,
    build_node_registry,
    build_table_index,
    render_content_user_prompt,
    build_prompt_cache_key,
    assemble_extraction,
    reconcile_reference_units,
    validate_section_ir,
    parse_sections,
    _parse_llm_json,
    _retry_feedback_suffix,
    _validate_section_result_shape,
    NODE_CENSUS_PROMPT_PATH,
    RELATION_PASS_PROMPT_PATH,
    SECTION_EXTRACTION_PROMPT_PATH,
    METADATA_PROMPT_PATH,
    REFERENCES_PROMPT_PATH,
    REFERENCES_BLOB_PROMPT_PATH,
    METADATA_SCHEMA_PATH,
    SECTION_ORDER,
    MAX_SECTION_RETRIES,
)
from tools.render_extraction import render_html

from production.config import Config
from production.llm import LLMClient
from production.outputs import ensure_paper_dir, save_json, write_status

logger = logging.getLogger(__name__)


async def process_paper(
    paper_path: Path,
    paper_id: str,
    config: Config,
    llm: LLMClient,
    paper_sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run the full extraction pipeline for a single paper, saving intermediates."""
    async with paper_sem:
        return await _run_paper_pipeline(paper_path, paper_id, config, llm)


async def _run_paper_pipeline(
    paper_path: Path,
    paper_id: str,
    config: Config,
    llm: LLMClient,
) -> dict[str, Any]:
    """Internal pipeline execution for one paper."""
    t0 = time.monotonic()
    paper_dir = ensure_paper_dir(config.output_dir, paper_id)
    write_status(paper_dir, "in_progress")

    try:
        paper_content = paper_path.read_text(encoding="utf-8")
        logger.info("[%s] Starting extraction (%d chars)", paper_id, len(paper_content))
        # The proxy prompt-cache routing key is unsupported on official DeepSeek (caching is
        # automatic, unknown params 400) — None there, so every stage's `prompt_cache_key=cache_key`
        # is skipped by the client's `if prompt_cache_key:` guard.
        cache_key = (
            build_prompt_cache_key(config.model, paper_content)
            if _supports_prompt_cache_kwargs(config.model)
            else None
        )

        # Phase 1 (stage A): node census + metadata + references in parallel
        census_result, metadata_result, references_result = await asyncio.gather(
            _run_census(paper_id, paper_content, cache_key, config, llm),
            _run_metadata(paper_id, paper_content, config, llm),
            _run_references(paper_id, paper_content, config, llm),
            return_exceptions=True,
        )

        # The census is required — propagate its error
        if isinstance(census_result, BaseException):
            raise census_result

        metadata = None
        references = None
        warnings: list[str] = []

        if isinstance(metadata_result, BaseException):
            warnings.append(f"metadata extraction failed: {metadata_result}")
            logger.warning("[%s] Metadata extraction failed: %s", paper_id, metadata_result)
        else:
            metadata = metadata_result

        if isinstance(references_result, BaseException):
            warnings.append(f"references extraction failed: {references_result}")
            logger.warning("[%s] References extraction failed: %s", paper_id, references_result)
        else:
            references = references_result

        # RF-01: dirname venue/year backfill + has_code/has_data — also recovers a usable
        # metadata record when the LLM metadata pass failed outright (metadata is None here).
        metadata = enrich_metadata(metadata, paper_id)

        census = normalize_census_nodes(census_result)
        census_issues = validate_census(census)
        if census_issues:
            details = "\n- ".join(census_issues)
            raise ValueError(f"Node census validation failed:\n- {details}")

        save_json(paper_dir / "01_census.json", census)
        save_json(paper_dir / "02_metadata.json", metadata)
        save_json(paper_dir / "03_references.json", references)
        logger.info("[%s] Phase 1 complete (census + metadata + references)", paper_id)

        # Phase 2 (stage B): relation pass over the full node set
        node_registry = build_node_registry(census)
        relation_output = await _run_relation_pass(
            paper_id, paper_content, node_registry, cache_key, config, llm
        )
        relations = relation_output.get("relations") if isinstance(relation_output, dict) else None
        if not isinstance(relations, list):
            relations = []
        save_json(
            paper_dir / "04_relations.json",
            {"relations": relations, "note": STAGE_B_RELATIONS_NOTE},
        )
        logger.info("[%s] Phase 2 complete (%d structural relations)", paper_id, len(relations))

        # Phase 3 (stage C): per-section content fill
        parsed_sections = parse_sections(paper_content)
        sections_included = sorted(
            [f"§{sid}" for sid in parsed_sections],
            key=lambda x: int(x[1:]),
        )
        section_results = await _run_all_content_sections(
            paper_id, paper_content, census, node_registry, relations,
            cache_key, config, llm, paper_dir,
        )
        logger.info("[%s] Phase 3 complete (%d content sections)", paper_id, len(section_results))

        # Assemble final extraction
        extraction = assemble_extraction(
            census, relations, section_results, paper_content,
            sections_included=sections_included,
            sections_omitted=[],
            verify_scores=config.verify_scores,
            blob_primary_evidence=config.blob_primary_evidence,
            blob_primary_references=config.blob_primary_references,
        )
        if references is not None:
            warnings.extend(reconcile_reference_units(references, extraction, census))
            # reconcile_reference_units mutates `references` in place to fill provides_unit_ids;
            # the Phase-1 save (03_references.json above) predates the spine, so re-persist the
            # linked version now — otherwise the on-disk references always show empty links.
            save_json(paper_dir / "03_references.json", references)
        save_json(paper_dir / "06_extraction.json", extraction)

        # Validate
        validation_issues = validate_section_ir(extraction, census=census)
        save_json(paper_dir / "07_validation.json", {
            "issues": validation_issues,
            "valid": len(validation_issues) == 0,
        })

        # Render HTML — a non-essential side artifact. Never fail a paper whose
        # extraction + validation already succeeded just because the renderer choked.
        try:
            pipeline_data = {
                "extraction": extraction,
                "metadata": metadata,
                "references": references,
            }
            html_path = paper_dir / "extraction.html"
            html_path.write_text(render_html(pipeline_data), encoding="utf-8")
        except Exception as render_exc:
            warnings.append(f"HTML render failed: {render_exc}")
            logger.warning(
                "[%s] HTML render failed (extraction is valid; skipping HTML): %s",
                paper_id, render_exc,
            )

        elapsed = time.monotonic() - t0
        token_usage = llm.drain_usage(paper_id)
        write_status(paper_dir, "completed", timing_s=round(elapsed, 1),
                     validation_issues=len(validation_issues), warnings=warnings,
                     token_usage=token_usage)
        logger.info(
            "[%s] Done (%.1fs, %d validation issues, %d tokens)",
            paper_id, elapsed, len(validation_issues), token_usage["totals"]["total_tokens"],
        )
        return {
            "paper_id": paper_id,
            "status": "completed",
            "timing_s": round(elapsed, 1),
            "validation_issues": len(validation_issues),
            "tokens": token_usage["totals"],
        }

    except Exception as exc:
        elapsed = time.monotonic() - t0
        # Drain on failure too: captures cost-to-failure (e.g. a truncated evidence pass)
        # and prevents the per-paper accumulator from leaking across a batch.
        token_usage = llm.drain_usage(paper_id)
        write_status(paper_dir, "failed", error=str(exc), timing_s=round(elapsed, 1),
                     token_usage=token_usage)
        logger.error("[%s] FAILED (%.1fs): %s", paper_id, elapsed, exc)
        return {
            "paper_id": paper_id,
            "status": "failed",
            "error": str(exc),
            "timing_s": round(elapsed, 1),
            "tokens": token_usage["totals"],
        }


async def _call_and_parse(
    llm: LLMClient,
    *,
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float,
    max_tokens: int,
    response_format: dict | None,
    paper_id: str,
    stage: str,
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    """Call the LLM and parse its JSON, re-issuing the call on a parse failure.

    `llm.call` already retries transport/truncation errors; this adds the parse-retry the
    content sections have so a single malformed-but-complete planning response re-issues the
    call instead of failing the whole paper. The census in particular is a hard dependency.
    """
    last_error: Exception | None = None
    for attempt in range(MAX_SECTION_RETRIES + 1):
        raw = await llm.call(
            model=model,
            system_prompt=system_prompt,
            user_content=user_content if last_error is None else user_content + _retry_feedback_suffix(last_error),
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            prompt_cache_key=prompt_cache_key,
            paper_id=paper_id,
            stage=stage,
        )
        try:
            return _parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < MAX_SECTION_RETRIES:
                logger.warning(
                    "[%s] %s attempt %d JSON parse error: %s — retrying call",
                    paper_id, stage, attempt + 1, exc,
                )
    raise RuntimeError(f"{stage} returned unparseable JSON after retries") from last_error


async def _run_census(
    paper_id: str, paper_content: str, cache_key: str | None, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run the node census (stage A)."""
    system_prompt, user_template = load_prompt(NODE_CENSUS_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = load_node_census_schema()
    resp_fmt = build_response_format(schema, name="node_census_output", model=config.model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, config.model)

    return await _call_and_parse(
        llm,
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        prompt_cache_key=cache_key,
        paper_id=paper_id,
        stage="census",
    )


async def _run_relation_pass(
    paper_id: str, paper_content: str, node_registry: list[dict[str, Any]],
    cache_key: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run the relation pass (stage B)."""
    system_prompt, user_template = load_prompt(RELATION_PASS_PROMPT_PATH)
    nodes_json = json.dumps(node_registry, ensure_ascii=False, indent=2)
    user_prompt = (
        user_template
        .replace("{{paper_content}}", paper_content)
        .replace("{{nodes_json}}", nodes_json)
    )
    schema = load_relation_pass_schema()
    resp_fmt = build_response_format(schema, name="relation_pass_output", model=config.model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, config.model)

    return await _call_and_parse(
        llm,
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        prompt_cache_key=cache_key,
        paper_id=paper_id,
        stage="relations",
    )


async def _run_metadata(
    paper_id: str, paper_content: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run metadata extraction."""
    system_prompt, user_template = load_prompt(METADATA_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", slice_metadata_input(paper_content))
    schema = json.loads(METADATA_SCHEMA_PATH.read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="metadata_output", model=config.model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, config.model)

    return await _call_and_parse(
        llm,
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        paper_id=paper_id,
        stage="metadata",
    )


async def _run_references(
    paper_id: str, paper_content: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run references extraction."""
    prompt_path = REFERENCES_BLOB_PROMPT_PATH if config.blob_primary_references else REFERENCES_PROMPT_PATH
    system_prompt, user_template = load_prompt(prompt_path)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    # Mode-adjusted: in blob mode the roles description says to skip background refs outright,
    # instead of contradicting the blob prompt with full-transcription guidance.
    schema = load_references_schema_for_mode(config.blob_primary_references)
    resp_fmt = build_response_format(schema, name="references_output", model=config.model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, config.model)

    return await _call_and_parse(
        llm,
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        paper_id=paper_id,
        stage="references",
    )


async def _run_all_content_sections(
    paper_id: str,
    paper_content: str,
    census: dict[str, Any],
    node_registry: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    cache_key: str,
    config: Config,
    llm: LLMClient,
    paper_dir: Path,
) -> list[dict[str, Any]]:
    """Run all three content sections (stage C) concurrently and save each result."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)
    spine_summary = census.get("spine_summary") if isinstance(census.get("spine_summary"), dict) else None

    def _section(section_type: str):
        return _extract_single_content_section(
            paper_id, paper_content, section_type, node_registry, relations,
            spine_summary, system_prompt, cache_key, config, llm, paper_dir,
        )

    if config.warm_content_cache and len(SECTION_ORDER) > 1:
        # P3 lever: run the cheapest section (SECTION_ORDER[0] = "problem") to completion first so
        # its [system+paper+spine+registry+relations] prefix populates the automatic prefix-cache;
        # the remaining sections then hit that warm prefix instead of racing it cold. Mirror
        # gather(return_exceptions=True) by capturing the warmer's exception so the loop below
        # stays aligned to SECTION_ORDER and aggregates errors identically.
        try:
            first: Any = await _section(SECTION_ORDER[0])
        except BaseException as exc:  # noqa: BLE001 — match gather's exception capture
            first = exc
        rest = await asyncio.gather(
            *(_section(s) for s in SECTION_ORDER[1:]), return_exceptions=True
        )
        results: list[Any] = [first, *rest]
    else:
        results = await asyncio.gather(
            *(_section(s) for s in SECTION_ORDER), return_exceptions=True
        )

    section_results: list[dict[str, Any]] = []
    errors: list[str] = []
    for section_type, result in zip(SECTION_ORDER, results):
        if isinstance(result, BaseException):
            errors.append(f"{section_type}: {result}")
        else:
            section_results.append(result)

    if errors:
        raise RuntimeError(
            f"Content extraction failed for {len(errors)} section(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return section_results


async def _extract_single_content_section(
    paper_id: str,
    paper_content: str,
    section_type: str,
    node_registry: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    spine_summary: dict[str, Any] | None,
    system_prompt: str,
    cache_key: str,
    config: Config,
    llm: LLMClient,
    paper_dir: Path,
) -> dict[str, Any]:
    """Extract a single content section with retry logic."""
    section_module = load_section_module(section_type, config.blob_primary_evidence)
    if config.blob_primary_evidence and section_type == "evidence":
        section_module = f"{section_module}\n\n## Source-table index\n{build_table_index(paper_content)}"
    section_schema = load_section_schema(section_type)
    if section_type == "evidence" and not config.blob_primary_evidence:
        # The committed evidence schema is the blob-primary contract; strip it back to the 0.11
        # shape so the opt-out arm's model never sees marker fields or the blob scores wording.
        section_schema = strip_blob_evidence_schema(section_schema)
    resp_fmt = build_response_format(section_schema, name=f"{section_type}_section", model=config.model)

    # json_object models (DeepSeek): fold the schema contract into section_focus so the shared
    # user-prompt prefix (paper/registry/relations) stays byte-identical across sections and the
    # cross-section cache stays warm. The system prompt is shared and stays untouched.
    if _structured_output_mode(config.model) == "json_object":
        section_module = f"{section_module}\n\n{schema_to_prompt_spec(section_schema)}"

    user_prompt = render_content_user_prompt(
        paper_content,
        section_type=section_type,
        section_module=section_module,
        node_registry=node_registry,
        relations=relations,
        spine_summary=spine_summary,
    )

    last_error: Exception | None = None
    for attempt in range(MAX_SECTION_RETRIES + 1):
        try:
            raw = await llm.call(
                model=config.model,
                system_prompt=system_prompt,
                user_content=user_prompt if last_error is None else user_prompt + _retry_feedback_suffix(last_error),
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                response_format=resp_fmt,
                prompt_cache_key=cache_key,
                paper_id=paper_id,
                stage=f"section:{section_type}",
            )
            result = _parse_llm_json(raw)
            _validate_section_result_shape(result, section_type)
            # RF-02: save the section content flat (top-level section_type/units/...). The legacy
            # {"section": {...}} wrapper made a naive top-level read return nothing — silent total
            # loss for any consumer that didn't know the container key. The in-memory contract
            # (assemble_extraction expects the wrapper) is unchanged.
            save_json(paper_dir / "05_sections" / f"{section_type}.json", result["section"])
            logger.debug("[%s] section:%s extracted successfully", paper_id, section_type)
            return result

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < MAX_SECTION_RETRIES:
                logger.warning(
                    "[%s] section:%s attempt %d parse error: %s",
                    paper_id, section_type, attempt + 1, exc,
                )

    raise RuntimeError(f"Content section {section_type} failed after retries") from last_error
