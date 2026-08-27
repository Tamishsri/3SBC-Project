"""Batch processing engine for the ATS Form Filler.

Processes an entire directory of candidate JSON files sequentially,
filling forms for each candidate and generating a consolidated report.

This module handles real-world scale: large numbers of candidates
with configurable rate limiting between runs to avoid bot detection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from src.api_client import load_candidate_from_file
from src.ats_router import get_filler
from src.browser import BrowserSession
from src.exceptions import ATSFillerError, UnsupportedATSError
from src.models import CandidateData, FillResult
from src.reporter import save_report
from src.tracker import append_to_tracker

logger = logging.getLogger(__name__)
console = Console(safe_box=True)


class BatchResult(NamedTuple):
    """Result for a single candidate in a batch run."""
    file_path: Path
    candidate_name: str
    success: bool
    fill_result: FillResult | None
    error: str | None


async def process_single_candidate(
    json_path: Path,
    port: int,
    url: str | None = None,
    human_mode: bool = False,
    multi_page: bool = False,
    screenshot: bool = False,
    delay_seconds: float = 5.0,
    webhook_url: str | None = None,
    preset: str | None = None,
    allow_generic: bool = False,
    detect_captcha: bool = False,
    generate_cover_letter: bool = False,
    interactive: bool = False,
) -> BatchResult:
    """Process a single candidate JSON file.

    Args:
        json_path: Path to the candidate JSON file.
        port: Browser debugging port.
        url: Optional URL to navigate to before filling.
        human_mode: Enable human-like typing.
        multi_page: Enable multi-step wizard auto-advancement.
        screenshot: Take screenshot after fill.
        delay_seconds: Seconds to wait BEFORE this candidate (rate limiting).
        webhook_url: Optional webhook URL to send completion notifications.
        preset: Optional user preference preset name to merge.
        allow_generic: Enable adaptive generic web form filler fallback.
        detect_captcha: Detect and pause for bot challenges.
        generate_cover_letter: Dynamically synthesize personalized cover letter from page.

    Returns:
        BatchResult with outcome details.
    """
    if delay_seconds > 0:
        logger.info("[BATCH] Waiting %.1fs before next candidate (rate limiting)...", delay_seconds)
        await asyncio.sleep(delay_seconds)

    try:
        candidate = load_candidate_from_file(str(json_path))
        if preset:
            from src.presets import merge_candidate_with_preset
            candidate = merge_candidate_with_preset(candidate, preset)
        name = candidate.personal.full_name
    except Exception as exc:
        return BatchResult(
            file_path=json_path,
            candidate_name=json_path.stem,
            success=False,
            fill_result=None,
            error=f"Failed to load/validate JSON: {exc}",
        )

    try:
        async with BrowserSession(port=port) as session:
            page = await session.get_active_page()

            if url:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception as e:
                    logger.warning("[BATCH] Navigation warning for %s: %s", name, e)

            if detect_captcha:
                from src.captcha_detector import handle_captcha_challenge
                await handle_captcha_challenge(page)

            if generate_cover_letter:
                from src.cover_letter_generator import augment_candidate_cover_letter
                candidate = await augment_candidate_cover_letter(candidate, page)

            filler = await get_filler(
                page,
                candidate,
                human_mode=human_mode,
                multi_page=multi_page,
                allow_generic=allow_generic,
                interactive=interactive,
                candidate_file=json_path,
            )
            result = await filler.fill()

            if screenshot:
                from src.main import take_screenshot
                await take_screenshot(page, prefix=f"batch_{json_path.stem}")

            save_report(result, candidate)
            append_to_tracker(result, candidate, json_path)

            from src.recovery import save_checkpoint
            save_checkpoint(batch_dir=json_path.parent, completed_file=json_path.name, success=not result.has_failures)

            if webhook_url:
                from src.notifier import send_fill_notification
                await send_fill_notification(webhook_url, result, candidate, notes=f"Batch: {json_path.stem}")

            return BatchResult(
                file_path=json_path,
                candidate_name=name,
                success=not result.has_failures,
                fill_result=result,
                error=None,
            )

    except UnsupportedATSError as exc:
        return BatchResult(
            file_path=json_path,
            candidate_name=name,
            success=False,
            fill_result=None,
            error=f"Unsupported ATS: {exc}",
        )
    except ATSFillerError as exc:
        return BatchResult(
            file_path=json_path,
            candidate_name=name,
            success=False,
            fill_result=None,
            error=str(exc),
        )
    except Exception as exc:
        logger.error("[BATCH] Error processing %s: %s", json_path.name, exc, exc_info=True)
        return BatchResult(
            file_path=json_path,
            candidate_name=name,
            success=False,
            fill_result=None,
            error=f"Unexpected error: {exc}",
        )


async def run_batch(
    batch_dir: Path,
    port: int,
    url: str | None = None,
    human_mode: bool = False,
    multi_page: bool = False,
    screenshot: bool = False,
    delay_seconds: float = 5.0,
    webhook_url: str | None = None,
    preset: str | None = None,
    allow_generic: bool = False,
    detect_captcha: bool = False,
    generate_cover_letter: bool = False,
    resume: bool = False,
    interactive: bool = False,
) -> list[BatchResult]:
    """Process all candidate JSON files in a directory.

    Files are processed sequentially (not in parallel) to avoid
    overwhelming the browser and triggering bot detection.

    Args:
        batch_dir: Directory containing candidate JSON files.
        port: Browser debugging port.
        url: Optional job URL to navigate to for each candidate.
        human_mode: Enable human-like typing for all candidates.
        multi_page: Enable multi-step wizard auto-advancement.
        screenshot: Take screenshot after each fill.
        delay_seconds: Rate-limit delay between candidates.
        webhook_url: Optional webhook URL for notifications.
        preset: Optional user preference preset name to merge.
        allow_generic: Enable adaptive generic web form filler fallback.
        detect_captcha: Detect and pause for bot challenges.
        generate_cover_letter: Dynamically synthesize personalized cover letter.
        resume: Resume from last saved batch recovery checkpoint.

    Returns:
        List of BatchResult for each candidate processed.
    """
    if resume:
        from src.recovery import get_remaining_batch_files
        json_files = get_remaining_batch_files(batch_dir)
    else:
        json_files = [f for f in sorted(batch_dir.glob("*.json")) if not f.name.startswith(".")]

    if not json_files:
        console.print(f"[yellow]No pending JSON files found in: {batch_dir}[/]")
        return []

    console.print()
    console.print(Panel(
        f"[bold cyan]BATCH MODE[/]\n"
        f"Directory: [dim]{batch_dir}[/]\n"
        f"Candidates: [bold]{len(json_files)}[/]\n"
        f"Rate limit: [dim]{delay_seconds}s between each[/]\n"
        f"Multi-page Wizard: [dim]{'ON' if multi_page else 'OFF'}[/]"
        + (f"\nGeneric Fallback: [dim]ON[/]" if allow_generic else "")
        + (f"\nResume Mode: [dim]ON[/]" if resume else "")
        + (f"\nPreset: [dim]{preset}[/]" if preset else "")
        + (f"\nWebhook: [dim]{webhook_url}[/]" if webhook_url else ""),
        title="[bold]Batch Processing",
        border_style="cyan",
    ))

    results: list[BatchResult] = []
    is_first = True

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing candidates...", total=len(json_files))

        for json_path in json_files:
            progress.update(task, description=f"Processing: [cyan]{json_path.name}[/]")
            result = await process_single_candidate(
                json_path=json_path,
                port=port,
                url=url,
                human_mode=human_mode,
                multi_page=multi_page,
                screenshot=screenshot,
                delay_seconds=0.0 if is_first else delay_seconds,
                webhook_url=webhook_url,
                preset=preset,
                allow_generic=allow_generic,
                detect_captcha=detect_captcha,
                generate_cover_letter=generate_cover_letter,
                interactive=interactive,
            )
            results.append(result)
            progress.advance(task)
            is_first = False

    _print_batch_summary(results)
    _save_batch_report(results, batch_dir)
    return results


def _print_batch_summary(results: list[BatchResult]) -> None:
    """Print a rich summary table of batch results."""
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    failed = total - succeeded

    table = Table(
        title=f"Batch Summary — {succeeded}/{total} successful",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Candidate", width=25)
    table.add_column("File", style="dim", width=30)
    table.add_column("Status", width=12)
    table.add_column("Rate", width=8, justify="right")
    table.add_column("Detail", width=20)

    for i, r in enumerate(results, 1):
        if r.success and r.fill_result:
            status = "[green]OK[/]"
            rate = f"[green]{r.fill_result.success_rate:.0f}%[/]"
            detail = f"{len(r.fill_result.filled_fields)} filled"
        elif r.fill_result:
            status = "[yellow]PARTIAL[/]"
            rate = f"[yellow]{r.fill_result.success_rate:.0f}%[/]"
            detail = f"{len(r.fill_result.failed_fields)} failed"
        else:
            status = "[red]ERROR[/]"
            rate = "[dim]N/A[/]"
            detail = (r.error or "")[:20]

        table.add_row(str(i), r.candidate_name, r.file_path.name, status, rate, detail)

    console.print()
    console.print(table)
    console.print()

    border = "green" if failed == 0 else ("yellow" if succeeded > 0 else "red")
    console.print(Panel(
        f"[bold]Batch complete:[/] {succeeded} succeeded, {failed} failed out of {total} total",
        border_style=border,
    ))


def _save_batch_report(results: list[BatchResult], batch_dir: Path) -> None:
    """Save a JSON batch summary report."""
    reports_dir = Path("fill_reports")
    reports_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"{ts}_batch_{batch_dir.name}.json"

    data = {
        "schema_version": "1.0",
        "type": "batch_report",
        "timestamp": datetime.now().isoformat(),
        "batch_directory": str(batch_dir),
        "total_candidates": len(results),
        "succeeded": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
        "candidates": [
            {
                "file": r.file_path.name,
                "name": r.candidate_name,
                "success": r.success,
                "success_rate_pct": r.fill_result.success_rate if r.fill_result else None,
                "filled_fields": r.fill_result.filled_fields if r.fill_result else [],
                "failed_fields": r.fill_result.failed_fields if r.fill_result else [],
                "error": r.error,
            }
            for r in results
        ],
    }

    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("[BATCH] Batch report saved: %s", report_path)
    console.print(f"[dim]Batch report: {report_path}[/]")
