"""Output directory management and resumability."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any


def ensure_paper_dir(output_dir: Path, paper_id: str) -> Path:
    """Create and return the per-paper output directory."""
    paper_dir = output_dir / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "04_sections").mkdir(exist_ok=True)
    return paper_dir


def is_paper_completed(output_dir: Path, paper_id: str) -> bool:
    """Check if a paper has already been successfully processed."""
    status_path = output_dir / paper_id / "status.json"
    if not status_path.exists():
        return False
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        return status.get("status") == "completed"
    except (json.JSONDecodeError, OSError):
        return False


def save_json(path: Path, data: Any) -> None:
    """Atomic JSON write — writes to temp file then renames."""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)


def write_status(paper_dir: Path, status: str, **extra: Any) -> None:
    """Write or update the paper status file."""
    data: dict[str, Any] = {"status": status, "updated_at": time.time()}
    data.update(extra)
    save_json(paper_dir / "status.json", data)


def write_run_summary(output_dir: Path, summary: dict[str, Any]) -> None:
    """Write the top-level run summary."""
    save_json(output_dir / "run_summary.json", summary)
