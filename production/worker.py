"""Per-paper async extraction pipeline (section-ir-0.7) with intermediate saves.

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
    load_prompt,
    load_node_census_schema,
    load_relation_pass_schema,
    load_section_schema,
    load_section_module,
    build_response_format,
    normalize_census_nodes,
    validate_census,
    build_node_registry,
    render_content_user_prompt,
    build_prompt_cache_key,
    assemble_extraction,
    reconcile_reference_units,
    validate_section_ir,
    parse_sections,
    _parse_llm_json,
    _validate_section_result_shape,
    NODE_CENSUS_PROMPT_PATH,
    RELATION_PASS_PROMPT_PATH,
    SECTION_EXTRACTION_PROMPT_PATH,
    METADATA_PROMPT_PATH,
    REFERENCES_PROMPT_PATH,
    METADATA_SCHEMA_PATH,
    REFERENCES_SCHEMA_PATH,
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
        cache_key = build_prompt_cache_key(config.model, paper_content)

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
        save_json(paper_dir / "04_relations.json", {"relations": relations})
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
        )
        if references is not None:
            warnings.extend(reconcile_reference_units(references, extraction))
        save_json(paper_dir / "06_extraction.json", extraction)

        # Validate
        validation_issues = validate_section_ir(extraction, census=census)
        save_json(paper_dir / "07_validation.json", {
            "issues": validation_issues,
            "valid": len(validation_issues) == 0,
        })

        # Render HTML
        pipeline_data = {
            "extraction": extraction,
            "metadata": metadata,
            "references": references,
        }
        html_path = paper_dir / "extraction.html"
        html_path.write_text(render_html(pipeline_data), encoding="utf-8")

        elapsed = time.monotonic() - t0
        write_status(paper_dir, "completed", timing_s=round(elapsed, 1),
                     validation_issues=len(validation_issues), warnings=warnings)
        logger.info(
            "[%s] Done (%.1fs, %d validation issues)",
            paper_id, elapsed, len(validation_issues),
        )
        return {
            "paper_id": paper_id,
            "status": "completed",
            "timing_s": round(elapsed, 1),
            "validation_issues": len(validation_issues),
        }

    except Exception as exc:
        elapsed = time.monotonic() - t0
        write_status(paper_dir, "failed", error=str(exc), timing_s=round(elapsed, 1))
        logger.error("[%s] FAILED (%.1fs): %s", paper_id, elapsed, exc)
        return {
            "paper_id": paper_id,
            "status": "failed",
            "error": str(exc),
            "timing_s": round(elapsed, 1),
        }


async def _run_census(
    paper_id: str, paper_content: str, cache_key: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run the node census (stage A)."""
    system_prompt, user_template = load_prompt(NODE_CENSUS_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = load_node_census_schema()
    resp_fmt = build_response_format(schema, name="node_census_output", model=config.model)

    raw = await llm.call(
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
    return _parse_llm_json(raw)


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

    raw = await llm.call(
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
    return _parse_llm_json(raw)


async def _run_metadata(
    paper_id: str, paper_content: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run metadata extraction."""
    system_prompt, user_template = load_prompt(METADATA_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = json.loads(METADATA_SCHEMA_PATH.read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="metadata_output", model=config.model)

    raw = await llm.call(
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        paper_id=paper_id,
        stage="metadata",
    )
    return _parse_llm_json(raw)


async def _run_references(
    paper_id: str, paper_content: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run references extraction."""
    system_prompt, user_template = load_prompt(REFERENCES_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = json.loads(REFERENCES_SCHEMA_PATH.read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="references_output", model=config.model)

    raw = await llm.call(
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        paper_id=paper_id,
        stage="references",
    )
    return _parse_llm_json(raw)


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
    """Run all four content sections (stage C) concurrently and save each result."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)
    spine_summary = census.get("spine_summary") if isinstance(census.get("spine_summary"), dict) else None

    tasks = [
        _extract_single_content_section(
            paper_id, paper_content, section_type, node_registry, relations,
            spine_summary, system_prompt, cache_key, config, llm, paper_dir,
        )
        for section_type in SECTION_ORDER
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

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
    section_module = load_section_module(section_type)
    user_prompt = render_content_user_prompt(
        paper_content,
        section_type=section_type,
        section_module=section_module,
        node_registry=node_registry,
        relations=relations,
        spine_summary=spine_summary,
    )
    section_schema = load_section_schema(section_type)
    resp_fmt = build_response_format(section_schema, name=f"{section_type}_section", model=config.model)

    last_error: Exception | None = None
    for attempt in range(MAX_SECTION_RETRIES + 1):
        try:
            raw = await llm.call(
                model=config.model,
                system_prompt=system_prompt,
                user_content=user_prompt,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                response_format=resp_fmt,
                prompt_cache_key=cache_key,
                paper_id=paper_id,
                stage=f"section:{section_type}",
            )
            result = _parse_llm_json(raw)
            _validate_section_result_shape(result, section_type)
            save_json(paper_dir / "05_sections" / f"{section_type}.json", result)
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
