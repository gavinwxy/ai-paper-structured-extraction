"""Batch extraction configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    input_dir: Path
    output_dir: Path
    model: str = "gemini-3-flash-preview-nothinking"
    base_url: str = "http://35.220.164.252:3888/v1"
    api_key: str = ""
    paper_concurrency: int = 10
    llm_concurrency: int = 30
    temperature: float = 0.0
    max_tokens: int = 65_536
    planning_max_tokens: int = 16_384
    max_retries: int = 3
    limit: int = 0
    force: bool = False
    log_level: str = "INFO"
