"""Per-paper async extraction pipeline with intermediate saves."""

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
    load_planning_schema,
    load_section_schema,
    load_section_module,
    build_response_format,
    normalize_planning_item_ids,
    validate_plan,
    build_planless_stubs,
    expand_section_plans,
    build_id_registry,
    render_section_user_prompt,
    build_prompt_cache_key,
    assemble_extraction,
    validate_section_ir,
    parse_sections,
    _parse_llm_json,
    _validate_section_result_shape,
    ValidationError,
    PLANNING_PROMPT_PATH,
    SECTION_EXTRACTION_PROMPT_PATH,
    METADATA_PROMPT_PATH,
    REFERENCES_PROMPT_PATH,
    METADATA_SCHEMA_PATH,
    REFERENCES_SCHEMA_PATH,
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

        # Phase 1: Planning + metadata + references in parallel
        plan_result, metadata_result, references_result = await asyncio.gather(
            _run_planning(paper_id, paper_content, config, llm),
            _run_metadata(paper_id, paper_content, config, llm),
            _run_references(paper_id, paper_content, config, llm),
            return_exceptions=True,
        )

        # Planning is required — propagate its error
        if isinstance(plan_result, BaseException):
            raise plan_result

        # Metadata and references are optional
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

        # Save phase 1 outputs
        save_json(paper_dir / "01_plan.json", plan_result)
        save_json(paper_dir / "02_metadata.json", metadata)
        save_json(paper_dir / "03_references.json", references)
        logger.info("[%s] Phase 1 complete (plan + metadata + references)", paper_id)

        # Normalize and validate plan
        normalized_plan = normalize_planning_item_ids(plan_result)
        plan_issues = validate_plan(normalized_plan)
        if plan_issues:
            details = "\n- ".join(plan_issues)
            raise ValueError(f"Planning validation failed:\n- {details}")
        plan = build_planless_stubs(normalized_plan)

        # Phase 2: Parallel section extraction
        section_plans = expand_section_plans(plan)
        if not section_plans:
            raise ValueError("Plan contains no sections to extract")

        id_registry = build_id_registry(plan)
        cache_key = build_prompt_cache_key(config.model, paper_content)
        parsed_sections = parse_sections(paper_content)
        sections_included = sorted(
            [f"§{sid}" for sid in parsed_sections],
            key=lambda x: int(x[1:]),
        )

        section_results = await _run_all_sections(
            paper_id, paper_content, plan, section_plans,
            id_registry, cache_key, config, llm, paper_dir,
        )
        logger.info("[%s] Phase 2 complete (%d sections extracted)", paper_id, len(section_results))

        # Assemble final extraction
        extraction = assemble_extraction(
            plan, section_results, paper_content,
            sections_included=sections_included,
            sections_omitted=[],
        )
        save_json(paper_dir / "05_extraction.json", extraction)

        # Validate
        validation_issues = validate_section_ir(extraction, plan=plan)
        save_json(paper_dir / "06_validation.json", {
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


async def _run_planning(
    paper_id: str, paper_content: str, config: Config, llm: LLMClient,
) -> dict[str, Any]:
    """Run the planning pass."""
    system_prompt, user_template = load_prompt(PLANNING_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = load_planning_schema()
    resp_fmt = build_response_format(schema, name="planning_output", model=config.model)

    raw = await llm.call(
        model=config.model,
        system_prompt=system_prompt,
        user_content=user_prompt,
        temperature=config.temperature,
        max_tokens=config.planning_max_tokens,
        response_format=resp_fmt,
        paper_id=paper_id,
        stage="planning",
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


async def _run_all_sections(
    paper_id: str,
    paper_content: str,
    plan: dict[str, Any],
    section_plans: list[dict[str, Any]],
    id_registry: list[dict[str, Any]],
    cache_key: str,
    config: Config,
    llm: LLMClient,
    paper_dir: Path,
) -> list[dict[str, Any]]:
    """Run all section extractions concurrently and save each result."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)

    tasks = []
    for i, section_plan in enumerate(section_plans):
        tasks.append(
            _extract_single_section(
                paper_id, paper_content, plan, section_plan,
                id_registry, system_prompt, cache_key, config, llm,
                paper_dir, index=i,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successful results, raise on any failure
    section_results: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            label = section_plans[i].get("section_type", f"section_{i}")
            errors.append(f"{label}: {result}")
        else:
            section_results.append(result)

    if errors:
        raise RuntimeError(
            f"Section extraction failed for {len(errors)} section(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return section_results


async def _extract_single_section(
    paper_id: str,
    paper_content: str,
    plan: dict[str, Any],
    section_plan: dict[str, Any],
    id_registry: list[dict[str, Any]],
    system_prompt: str,
    cache_key: str,
    config: Config,
    llm: LLMClient,
    paper_dir: Path,
    index: int = 0,
) -> dict[str, Any]:
    """Extract a single section with retry logic."""
    section_type = section_plan.get("section_type", "unknown")
    section_module = load_section_module(section_type)
    user_prompt = render_section_user_prompt(
        paper_content,
        id_registry=id_registry,
        section_plan=section_plan,
        section_module=section_module,
        spine_summary=plan.get("spine_summary") if isinstance(plan.get("spine_summary"), dict) else None,
    )
    section_schema = load_section_schema(section_type)
    resp_fmt = build_response_format(section_schema, name=f"{section_type}_section", model=config.model)

    segment_label = section_plan.get("segment_label", "")
    stage = f"section:{section_type}" + (f"/{segment_label}" if segment_label else "")

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
                stage=stage,
            )
            result = _parse_llm_json(raw)
            _validate_section_result_shape(result, section_plan)

            # Save individual section output
            filename = f"{section_type}.json"
            if segment_label:
                filename = f"{section_type}_{segment_label}.json"
            save_json(paper_dir / "04_sections" / filename, result)

            logger.debug("[%s] %s extracted successfully", paper_id, stage)
            return result

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < MAX_SECTION_RETRIES:
                logger.warning(
                    "[%s] %s attempt %d parse error: %s",
                    paper_id, stage, attempt + 1, exc,
                )

    raise RuntimeError(f"Section {stage} failed after retries") from last_error
