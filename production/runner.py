"""Async batch orchestrator — discovers papers, manages concurrency, reports results."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from production.config import Config
from production.llm import LLMClient
from production.outputs import is_paper_completed, write_run_summary
from production.progress import ProgressTracker
from production.worker import process_paper

# After production.worker: importing it puts the project root on sys.path, which makes the
# top-level section_pipeline module importable regardless of the caller's cwd.
from section_pipeline import build_output_manifest

logger = logging.getLogger(__name__)


def discover_papers(input_dir: Path) -> list[tuple[str, Path]]:
    """Find all .md files in input_dir and return (paper_id, path) pairs sorted by name."""
    papers = []
    for path in sorted(input_dir.glob("*.md")):
        paper_id = path.stem
        papers.append((paper_id, path))
    return papers


async def run_batch(config: Config) -> dict[str, Any]:
    """Main entry point: discover papers, filter already-done, process in parallel."""
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # RF-19: ship the data dictionary beside the outputs so a consumer (human or agent) pointed
    # at the run root learns the file contracts without trial-and-error. Overwritten per run —
    # it documents the flags the freshest papers were produced with.
    manifest = build_output_manifest(
        blob_primary_evidence=config.blob_primary_evidence,
        blob_primary_references=config.blob_primary_references,
        verify_scores=config.verify_scores,
        model=config.model,
    )
    (config.output_dir / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Discover papers
    all_papers = discover_papers(config.input_dir)
    if not all_papers:
        logger.error("No .md files found in %s", config.input_dir)
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
