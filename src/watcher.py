"""Drop-Folder Inbox Watcher Daemon for ATS Form Filler.

Continuously monitors a directory (e.g. `inbox/`) for dropped resume files
(`.pdf`, `.txt`, `.json`). Automatically parses, validates, and triggers
form filling on the active browser tab without requiring manual CLI invocations.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel

from src.api_client import load_candidate_from_file
from src.ats_router import get_filler
from src.browser import BrowserSession
from src.captcha_detector import handle_captcha_challenge
from src.cover_letter_generator import augment_candidate_cover_letter
from src.models import CandidateData, FillResult
from src.reporter import save_report
from src.resume_fallback import extract_text_from_file, parse_resume_text
from src.tracker import append_to_tracker

logger = logging.getLogger(__name__)
console = Console(safe_box=True)


async def process_inbox_file(
    file_path: Path,
    port: int = 9222,
    human_mode: bool = False,
    multi_page: bool = True,
    allow_generic: bool = True,
    detect_captcha: bool = True,
    generate_cover_letter: bool = True,
    interactive: bool = False,
    move_to_processed: bool = True,
    processed_dir: Path | None = None,
) -> FillResult | None:
    """Process a single file dropped into the inbox."""
    console.print(Panel(
        f"[bold cyan]📥 New Candidate File Detected:[/] [white]{file_path.name}[/]\n"
        f"[dim]Path: {file_path}[/]",
        title="[bold cyan]Inbox Auto-Watcher Active[/]",
        border_style="cyan",
    ))

    # 1. Load / Parse Candidate
    candidate: CandidateData | None = None
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".json":
            candidate = load_candidate_from_file(str(file_path))
        elif suffix in (".pdf", ".txt", ".md"):
            raw_text = extract_text_from_file(file_path)
            candidate = parse_resume_text(raw_text, source_file=str(file_path))
            json_cache = file_path.with_suffix(".json")
            json_cache.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")
        else:
            console.print(f"[yellow]Skipping unsupported file type:[/] {file_path.name}")
            return None
    except Exception as exc:
        console.print(f"[bold red]❌ Failed to parse candidate file:[/] {exc}")
        return None

    console.print(f"[green]✅ Candidate ready:[/] [bold]{candidate.personal.full_name}[/] ({candidate.personal.email})")

    # 2. Connect to Browser CDP
    try:
        session = BrowserSession(port=port)
        page = await session.connect()
    except Exception as exc:
        console.print(f"[bold red]❌ Could not connect to browser on port {port}:[/] {exc}")
        console.print("[dim]Make sure Chrome is running with remote debugging enabled (launch_browser.bat).[/]")
        return None

    try:
        # CAPTCHA check
        if detect_captcha:
            await handle_captcha_challenge(page)

        # Cover letter check
        if generate_cover_letter and not candidate.cover_letter:
            candidate = await augment_candidate_cover_letter(candidate, page)

        # Get filler and execute
        filler = await get_filler(
            page=page,
            candidate=candidate,
            human_mode=human_mode,
            multi_page=multi_page,
            allow_generic=allow_generic,
            interactive=interactive,
            candidate_file=file_path if suffix == ".json" else None,
        )

        result = await filler.fill()

        # Save report & tracker
        report_path = save_report(result, candidate, source_file=str(file_path))
        append_to_tracker(result, candidate, source_file=file_path)

        console.print(f"[bold green]✨ Form filled successfully![/] Score: {result.success_rate:.0f}%")

        # Move to processed folder if requested
        if move_to_processed:
            dest_dir = processed_dir or (file_path.parent / "processed")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / file_path.name
            shutil.move(str(file_path), str(dest_file))
            console.print(f"[dim]Moved {file_path.name} -> {dest_file}[/]")

        return result

    except Exception as exc:
        logger.error("[INBOX WATCHER] Error processing %s: %s", file_path.name, exc)
        console.print(f"[bold red]❌ Fill error for {file_path.name}:[/] {exc}")
        return None
    finally:
        await session.disconnect()


async def run_inbox_watcher(
    watch_dir: str | Path = "inbox",
    port: int = 9222,
    human_mode: bool = False,
    multi_page: bool = True,
    allow_generic: bool = True,
    detect_captcha: bool = True,
    generate_cover_letter: bool = True,
    interactive: bool = False,
    poll_interval: float = 2.0,
    max_events: int | None = None,
    on_event_processed: Callable[[Path, FillResult | None], None] | None = None,
) -> None:
    """Run the inbox folder watcher loop."""
    inbox_path = Path(watch_dir).resolve()
    inbox_path.mkdir(parents=True, exist_ok=True)
    processed_dir = inbox_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold green]Folder:[/] [white]{inbox_path}[/]\n"
        f"[bold green]Supported Formats:[/] [dim].pdf, .txt, .json, .md[/]\n"
        f"[bold green]Browser Port:[/] [dim]{port}[/]\n"
        f"[bold green]Generic Web Forms:[/] [dim]{'ON' if allow_generic else 'OFF'}[/]\n"
        f"[bold green]Interactive Learning:[/] [dim]{'ON' if interactive else 'OFF'}[/]\n\n"
        f"[dim]Drop any resume file into this directory to automatically trigger form filling on your active Chrome tab.[/]",
        title="[bold green]📁 ATS Form Filler -- Drop-Folder Watcher Daemon[/]",
        border_style="green",
    ))

    seen_files: set[str] = set()
    events_count = 0

    try:
        while True:
            # Look for non-hidden files in inbox
            candidates = [
                f for f in sorted(inbox_path.iterdir())
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".json", ".pdf", ".txt", ".md")
            ]

            for cand_file in candidates:
                if cand_file.name not in seen_files:
                    seen_files.add(cand_file.name)
                    res = await process_inbox_file(
                        cand_file,
                        port=port,
                        human_mode=human_mode,
                        multi_page=multi_page,
                        allow_generic=allow_generic,
                        detect_captcha=detect_captcha,
                        generate_cover_letter=generate_cover_letter,
                        interactive=interactive,
                        processed_dir=processed_dir,
                    )
                    events_count += 1
                    if on_event_processed:
                        on_event_processed(cand_file, res)

                    if max_events and events_count >= max_events:
                        return

            await asyncio.sleep(poll_interval)
    except (asyncio.CancelledError, KeyboardInterrupt):
        console.print("\n[dim]Inbox watcher stopped by user.[/]")
