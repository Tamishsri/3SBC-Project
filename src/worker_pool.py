"""Concurrent worker pool for handling heavy parallel data flow and multi-task jobs.

Dispatches candidate form filling tasks across concurrent asynchronous workers
with strict concurrency throttling (semaphore), dedicated tab isolation per task,
and backpressure protection against browser overload.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Coroutine, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.api_client import load_candidate_from_file
from src.ats_router import get_filler
from src.browser import BrowserSession
from src.models import CandidateData, FillResult
from src.reporter import save_report
from src.tracker import append_to_tracker

logger = logging.getLogger(__name__)
console = Console(safe_box=True)


@dataclass
class TaskItem:
    """Individual work item for a candidate and target job."""
    task_id: str
    data_file: Path
    job_url: str | None = None
    user_id: str = "default"
    human_mode: bool = False
    multi_page: bool = False
    screenshot: bool = False
    webhook_url: str | None = None
    preset: str | None = None


@dataclass
class TaskOutcome:
    """Result of an executed worker task."""
    task_id: str
    candidate_name: str
    user_id: str
    success: bool
    fill_result: FillResult | None
    error: str | None = None
    duration_seconds: float = 0.0


class ConcurrentWorkerPool:
    """Manages concurrent execution of form filling tasks with isolation."""

    def __init__(self, max_concurrency: int = 3, port: int = 9222) -> None:
        self.max_concurrency = max_concurrency
        self.port = port
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.outcomes: list[TaskOutcome] = []

    async def _execute_worker_task(self, session: BrowserSession, item: TaskItem) -> TaskOutcome:
        """Execute a single task with an isolated tab under semaphore control."""
        async with self.semaphore:
            start_time = asyncio.get_event_loop().time()
            logger.info("[POOL] Worker acquired slot for task %s (User: %s)", item.task_id, item.user_id)

            # 1. Load candidate
            try:
                candidate = load_candidate_from_file(str(item.data_file))
                if item.preset:
                    from src.presets import merge_candidate_with_preset
                    candidate = merge_candidate_with_preset(candidate, item.preset)
                cand_name = candidate.personal.full_name
            except Exception as exc:
                return TaskOutcome(
                    task_id=item.task_id,
                    candidate_name=item.data_file.stem,
                    user_id=item.user_id,
                    success=False,
                    fill_result=None,
                    error=f"Failed loading candidate JSON: {exc}",
                )

            # 2. Open dedicated isolated tab for this worker
            page = None
            try:
                page = await session.create_isolated_page(item.job_url)

                filler = await get_filler(page, candidate, human_mode=item.human_mode, multi_page=item.multi_page)
                result = await filler.fill()

                if item.screenshot:
                    from src.main import take_screenshot
                    await take_screenshot(page, prefix=f"user_{item.user_id}_{item.task_id}")

                # Save report and append to tracker safely
                save_report(result, candidate)
                append_to_tracker(
                    result,
                    candidate,
                    source_file=item.data_file,
                    notes=f"User: {item.user_id} | Task: {item.task_id}",
                )

                if item.webhook_url:
                    from src.notifier import send_fill_notification
                    await send_fill_notification(
                        item.webhook_url,
                        result,
                        candidate,
                        notes=f"User: {item.user_id} | Task: {item.task_id}",
                    )

                duration = asyncio.get_event_loop().time() - start_time
                return TaskOutcome(
                    task_id=item.task_id,
                    candidate_name=cand_name,
                    user_id=item.user_id,
                    success=not result.has_failures,
                    fill_result=result,
                    duration_seconds=duration,
                )

            except Exception as exc:
                duration = asyncio.get_event_loop().time() - start_time
                logger.error("[POOL] Worker task %s failed: %s", item.task_id, exc)
                return TaskOutcome(
                    task_id=item.task_id,
                    candidate_name=cand_name,
                    user_id=item.user_id,
                    success=False,
                    fill_result=None,
                    error=str(exc),
                    duration_seconds=duration,
                )

            finally:
                # Keep page open if user needs to review, or close if headless batch
                pass

    async def run_tasks(self, tasks: list[TaskItem]) -> list[TaskOutcome]:
        """Dispatch all tasks concurrently up to max_concurrency limit.

        Args:
            tasks: List of TaskItem objects to execute.

        Returns:
            List of TaskOutcome for all completed tasks.
        """
        if not tasks:
            return []

        console.print()
        console.print(Panel(
            f"[bold cyan]CONCURRENT WORKER POOL[/]\n"
            f"Active Workers / Max Concurrency: [bold]{self.max_concurrency}[/]\n"
            f"Total Tasks Queued: [bold]{len(tasks)}[/]\n"
            f"Browser CDP Port: [dim]{self.port}[/]",
            title="[bold]High-Throughput Concurrent Processing",
            border_style="cyan",
        ))

        async with BrowserSession(port=self.port) as session:
            # Create concurrent coroutines
            coros = [self._execute_worker_task(session, item) for item in tasks]
            self.outcomes = await asyncio.gather(*coros)

        self._print_pool_summary()
        return self.outcomes

    def _print_pool_summary(self) -> None:
        """Display consolidated metrics from the concurrent worker pool."""
        total = len(self.outcomes)
        succeeded = sum(1 for o in self.outcomes if o.success)
        failed = total - succeeded

        table = Table(
            title=f"Worker Pool Summary — {succeeded}/{total} Successful ({self.max_concurrency} workers)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Task ID", style="dim", width=12)
        table.add_column("User ID", style="cyan", width=12)
        table.add_column("Candidate", width=22)
        table.add_column("Status", width=10)
        table.add_column("Rate", width=8, justify="right")
        table.add_column("Duration", width=10, justify="right")

        for o in self.outcomes:
            if o.success and o.fill_result:
                status = "[green]OK[/]"
                rate = f"[green]{o.fill_result.success_rate:.0f}%[/]"
            elif o.fill_result:
                status = "[yellow]PARTIAL[/]"
                rate = f"[yellow]{o.fill_result.success_rate:.0f}%[/]"
            else:
                status = "[red]ERROR[/]"
                rate = "[dim]0%[/]"

            dur_str = f"{o.duration_seconds:.1f}s"
            table.add_row(o.task_id, o.user_id, o.candidate_name, status, rate, dur_str)

        console.print()
        console.print(table)
        console.print()
