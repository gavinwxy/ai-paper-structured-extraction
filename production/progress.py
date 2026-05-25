"""Live progress tracking with periodic console output."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProgressTracker:
    total: int
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: float = field(default_factory=time.time)
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def processed(self) -> int:
        return self.completed + self.failed

    @property
    def remaining(self) -> int:
        return self.total - self.skipped - self.processed

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> float | None:
        if self.processed == 0:
            return None
        rate = self.processed / self.elapsed
        return self.remaining / rate if rate > 0 else None

    def mark_completed(self) -> None:
        self.completed += 1

    def mark_failed(self) -> None:
        self.failed += 1

    def mark_skipped(self) -> None:
        self.skipped += 1

    def _format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.0f}m"
        hours = minutes / 60
        return f"{hours:.1f}h"

    def log_progress(self) -> None:
        pct = (self.processed / max(self.total - self.skipped, 1)) * 100
        eta = self.eta_seconds
        eta_str = f" | ETA: ~{self._format_time(eta)}" if eta is not None else ""
        logger.info(
            "Progress: %d/%d (%.1f%%) | %d failed | elapsed: %s%s",
            self.processed,
            self.total - self.skipped,
            pct,
            self.failed,
            self._format_time(self.elapsed),
            eta_str,
        )

    async def _periodic_report(self, interval: float = 10.0) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                self.log_progress()
        except asyncio.CancelledError:
            pass

    def start_reporting(self, interval: float = 10.0) -> None:
        self._task = asyncio.create_task(self._periodic_report(interval))

    def stop_reporting(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def summary(self) -> dict:
        return {
            "total_papers": self.total,
            "skipped": self.skipped,
            "processed": self.processed,
            "completed": self.completed,
            "failed": self.failed,
            "elapsed_s": round(self.elapsed, 1),
            "papers_per_minute": round(self.processed / max(self.elapsed / 60, 0.01), 1),
        }
