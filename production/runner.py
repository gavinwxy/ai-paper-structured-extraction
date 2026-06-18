"""Async batch orchestrator — discovers papers, manages concurrency, reports results."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from production.config import Config
from production.llm import LLMClient
from production.outputs import is_paper_completed, write_run_summary
from production.progress import ProgressTracker
from production.worker import process_paper

# After production.worker: importing it puts the project root on sys.path, which makes the
# top-level section_pipeline module (and the tools/ namespace package) importable regardless
# of the caller's cwd.
from section_pipeline import build_output_manifest
from tools.parsed_blocks_to_markdown import SUPPORTED_SUFFIXES, convert_to_markdown

logger = logging.getLogger(__name__)

# Subdir under the output dir where json/jsonl inputs are converted to [§N]-marked Markdown.
# Leading underscore groups it with the other run-meta artifacts (_manifest.json) and keeps it
# out of discover_papers' *.md glob of the *source* dir.
PREPARED_SUBDIR = "_prepared_markdown"


def discover_papers(input_dir: Path) -> list[tuple[str, Path]]:
    """Find all .md files in input_dir and return (paper_id, path) pairs sorted by name."""
    papers = []
    for path in sorted(input_dir.glob("*.md")):
        paper_id = path.stem
        papers.append((paper_id, path))
    return papers


def _has_convertible_inputs(input_dir: Path) -> bool:
    """True if input_dir holds at least one json/jsonl file the converter can ingest."""
    return any(
        p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        for p in input_dir.iterdir()
    )


def prepare_markdown_inputs(config: Config) -> Path:
    """Resolve the directory of *.md papers to extract from, preprocessing json/jsonl on demand.

    - "md": return input_dir unchanged (historical contract — discover *.md directly).
    - "json"/"jsonl": convert those parsed-block inputs into [§N]-marked Markdown under
      <output_dir>/_prepared_markdown and return that dir.
    - "auto": if input_dir already holds any *.md, use it as-is; else convert whatever json/jsonl
      it finds. With nothing convertible either, fall through to input_dir so discover_papers
      reports the usual "no papers" error.

    Conversion is deterministic and LLM-free, so it re-runs each batch (cheap, and it picks up
    source edits); the persistent _prepared_markdown dir keeps the exact [§N] inputs inspectable.
    """
    fmt = config.input_format
    if fmt == "md":
        return config.input_dir

    if fmt == "auto":
        if any(config.input_dir.glob("*.md")):
            logger.info("input-format=auto: using existing *.md in %s as-is", config.input_dir)
            return config.input_dir
        if not _has_convertible_inputs(config.input_dir):
            return config.input_dir

    prepared_dir = config.output_dir / PREPARED_SUBDIR
    written = convert_to_markdown(
        config.input_dir,
        prepared_dir,
        input_type=("auto" if fmt == "auto" else fmt),
        include_metadata=False,
    )
    logger.info(
        "Preprocessed %d %s document(s) from %s -> %s",
        len(written), fmt, config.input_dir, prepared_dir,
    )
    return prepared_dir


async def run_batch(config: Config) -> dict[str, Any]:
    """Main entry point: discover papers, filter already-done, process in parallel."""
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # RF-19: ship the data dictionary beside the outputs so a consumer (human or agent) pointed
    # at the run root learns the file contracts without trial-and-error. Overwritten per run —
    # it documents the flags the freshest papers were produced with.
    manifest = build_output_manifest(
        verify_scores=config.verify_scores,
        model=config.model,
    )
    (config.output_dir / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Resolve the markdown source dir — preprocessing json/jsonl into [§N]-marked Markdown when
    # --input-format requests it. A preprocessing failure is fatal for the batch (no papers to run).
    try:
        source_dir = prepare_markdown_inputs(config)
    except Exception as exc:
        logger.error("Input preprocessing failed for %s: %s", config.input_dir, exc)
        return {"error": f"input preprocessing failed: {exc}"}

    # Discover papers
    all_papers = discover_papers(source_dir)
    if not all_papers:
        logger.error("No .md files found in %s", source_dir)
        return {"error": "No papers found"}

    if config.limit > 0:
        all_papers = all_papers[:config.limit]

    logger.info(
        "Discovered %d papers in %s", len(all_papers), config.input_dir,
    )

    # Filter already-completed (resumability)
    if config.force:
        papers_to_process = all_papers
        skipped = 0
    else:
        papers_to_process = []
        skipped = 0
        for paper_id, path in all_papers:
            if is_paper_completed(config.output_dir, paper_id):
                skipped += 1
            else:
                papers_to_process.append((paper_id, path))

    if skipped > 0:
        logger.info("Resumability: skipping %d already-completed papers", skipped)

    if not papers_to_process:
        logger.info("All papers already processed. Use --force to reprocess.")
        return {"total": len(all_papers), "skipped": len(all_papers), "processed": 0}

    logger.info(
        "Processing %d papers (concurrency: %d papers, %d LLM calls)",
        len(papers_to_process), config.paper_concurrency, config.llm_concurrency,
    )

    # Initialize LLM client and progress tracker
    llm = LLMClient(
        base_url=config.base_url,
        api_key=config.api_key,
        max_concurrency=config.llm_concurrency,
        max_retries=config.max_retries,
    )
    paper_sem = asyncio.Semaphore(config.paper_concurrency)
    progress = ProgressTracker(total=len(all_papers), skipped=skipped)
    progress.start_reporting(interval=15.0)

    # Launch all paper tasks
    async def _process_and_track(paper_id: str, path: Path) -> dict[str, Any]:
        result = await process_paper(path, paper_id, config, llm, paper_sem)
        if result["status"] == "completed":
            progress.mark_completed()
        else:
            progress.mark_failed()
        return result

    tasks = [
        _process_and_track(paper_id, path)
        for paper_id, path in papers_to_process
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Stop progress reporting
    progress.stop_reporting()
    await llm.close()

    # Collect final results
    paper_results: list[dict[str, Any]] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            paper_id = papers_to_process[i][0]
            logger.error("[%s] Unexpected error: %s", paper_id, result)
            # This task never reached _process_and_track's accounting — count it here so
            # progress.summary() (and the exit code derived from it) matches paper_results.
            progress.mark_failed()
            paper_results.append({
                "paper_id": paper_id,
                "status": "failed",
                "error": str(result),
            })
        else:
            paper_results.append(result)

    # Summary
    token_totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "cached_prompt_tokens": 0}
    for r in paper_results:
        for k, v in (r.get("tokens") or {}).items():
            if k == "truncated":
                continue
            if isinstance(v, (int, float)):
                token_totals[k] = token_totals.get(k, 0) + v
    # Papers where at least one pass hit the max_tokens ceiling (finish_reason=length); now a
    # fail-fast (1x, not 4x). Surfaced so ceiling hits are visible without inspecting each status.json.
    truncated_papers = sum(1 for r in paper_results if (r.get("tokens") or {}).get("truncated"))
    summary = {
        **progress.summary(),
        "llm_stats": llm.stats,
        "token_totals": token_totals,
        "truncated_papers": truncated_papers,
        "model": config.model,
        "base_url": config.base_url,
        "paper_results": paper_results,
    }
    write_run_summary(config.output_dir, summary)

    # Log final report
    progress.log_progress()
    logger.info(
        "Batch complete: %d/%d succeeded, %d failed (%.1fs total)",
        progress.completed, progress.processed, progress.failed, progress.elapsed,
    )
    if progress.failed > 0:
        failed_ids = [r["paper_id"] for r in paper_results if r.get("status") == "failed"]
        logger.info("Failed papers: %s", ", ".join(failed_ids[:20]))

    return summary
