"""CLI entry point for batch extraction."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
import os

from production.config import Config
from production.runner import run_batch


def setup_logging(output_dir: Path, level: str = "INFO") -> None:
    """Configure dual logging: file (DEBUG) + console (level)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Suppress noisy HTTP request logs from openai/httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # File handler — full debug output
    file_handler = logging.FileHandler(output_dir / "run.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Console handler — progress-focused
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console_handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="production",
        description="Batch extraction tool for section-IR pipeline",
    )
    parser.add_argument("input_dir", type=Path, help="Directory of paper files (.md by default; .json/.jsonl with --input-format)")
    parser.add_argument("output_dir", type=Path, help="Output directory for results")
    parser.add_argument(
        "--input-format",
        choices=("md", "auto", "json", "jsonl"),
        default="md",
        help="Input format (default: md = discover *.md directly). json/jsonl preprocess parsed-block "
             "inputs into [§N]-marked Markdown under <output_dir>/_prepared_markdown first; auto uses "
             "any *.md present, else converts the json/jsonl it finds.",
    )
    parser.add_argument("--model", default="qwen3.5-35b-a3b", help="Model name (default: qwen3.5-35b-a3b, run with thinking disabled)")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL")
    parser.add_argument("--paper-concurrency", type=int, default=10, help="Max papers in flight (default: 10)")
    parser.add_argument("--llm-concurrency", type=int, default=30, help="Max concurrent LLM calls (default: 30)")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature (default: 0.0)")
    parser.add_argument("--max-tokens", type=int, default=32_768, help="Max tokens for section extraction (default: 32768, proxy-safe)")
    parser.add_argument("--planning-max-tokens", type=int, default=24_576, help="Max tokens for planning/aux calls — census, relations, metadata, references (default: 24576)")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per LLM call (default: 3)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Console log level")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N papers (0=all)")
    parser.add_argument("--force", action="store_true", help="Reprocess all papers (ignore resumability)")
    parser.add_argument("--no-verify-scores", dest="verify_scores", action="store_false",
                        help="Disable the score-fidelity audit (transcribed values vs source tables)")
    parser.add_argument("--keep-references-in-body", dest="keep_references_in_body", action="store_true",
                        help="Feed the full paper (bibliography included) to the census/relations/section "
                             "passes. Default strips references-and-after from those stages' input "
                             "(citation layer + assembly always see the full paper). This is the A/B opt-out.")
    parser.add_argument("--warm-content-cache", dest="warm_content_cache", action="store_true",
                        default=True,
                        help="P3 cost lever (ON by default): run the first content section first to "
                             "warm the shared paper prefix so the rest hit the prefix-cache (saves "
                             "~6 pct eff-cost on cold proxies, costs one section of serial latency)")
    parser.add_argument("--no-warm-content-cache", dest="warm_content_cache", action="store_false",
                        help="Disable P3 warming — run all three content sections fully concurrently "
                             "(use when latency matters or the proxy is demonstrably warm)")
    return parser.parse_args()


def main() -> None:
    load_dotenv()

    args = parse_args()

    if not args.input_dir.is_dir():
        print(f"Error: input directory does not exist: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("API_KEY") or os.getenv("API-KEY", "")
    base_url = args.base_url or os.getenv("BASE_URL", "http://35.220.164.252:3888/v1")

    config = Config(
        input_dir=args.input_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        input_format=args.input_format,
        model=args.model,
        base_url=base_url,
        api_key=api_key,
        paper_concurrency=args.paper_concurrency,
        llm_concurrency=args.llm_concurrency,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        planning_max_tokens=args.planning_max_tokens,
        max_retries=args.max_retries,
        limit=args.limit,
        force=args.force,
        log_level=args.log_level,
        verify_scores=args.verify_scores,
        keep_references_in_body=args.keep_references_in_body,
        warm_content_cache=args.warm_content_cache,
    )

    setup_logging(config.output_dir, config.log_level)

    logging.getLogger(__name__).info(
        "Starting batch: %s -> %s (model=%s)",
        config.input_dir, config.output_dir, config.model,
    )

    summary = asyncio.run(run_batch(config))

    # An error summary (e.g. no papers discovered) carries no "failed" count — it must still
    # exit non-zero, or a mis-pointed batch/CI run looks like a clean success.
    if summary.get("failed", 0) > 0 or summary.get("error"):
        sys.exit(1)
