"""CLI entry point for the ATS Form Filler.

Orchestrates the entire flow:
1. Parse CLI arguments
2. Load configuration
3. Fetch & validate candidate data (HALT if invalid)
4. Connect to browser via CDP (HALT if connection fails)
5. Detect ATS platform & route to filler
6. Fill the form (or dry-run preview)
7. Take screenshot & save session report
8. HALT for human review — NEVER submit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 stdout/stderr on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.api_client import fetch_candidate_data, load_candidate_from_file
from src.ats_router import get_filler, _FILLER_CLASSES
from src.browser import BrowserSession
from src.config import Config, get_config
from src.exceptions import ATSFillerError
from src.reporter import save_report

console = Console(safe_box=True)
logger = logging.getLogger("ats_filler")


def setup_logging(level: str = "INFO") -> None:
    """Configure rich logging for clean terminal output."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="ats-filler",
        description="Semi-Automated ATS Form Filler - Pre-fills job applications without submitting.",
        epilog="[!] This tool NEVER auto-submits. You always review and submit manually.",
    )

    # Data source (mutually exclusive)
    data_group = parser.add_mutually_exclusive_group(required=False)
    data_group.add_argument(
        "--candidate-id",
        type=str,
        help="Candidate ID to fetch from the backend API",
    )
    data_group.add_argument(
        "--data-file",
        type=str,
        help="Path to a local JSON file with candidate data (for testing)",
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Override the API base URL (default: from .env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Browser debugging port (default: 9222)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Navigate to this URL before filling (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what WOULD be filled without touching the browser",
    )
    parser.add_argument(
        "--list-tabs",
        action="store_true",
        help="List all open browser tabs and exit",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Take a screenshot after filling (saved to screenshots/ folder)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip saving the JSON session report",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    # Validate: data source required unless --list-tabs or --dry-run
    if not args.list_tabs and not args.candidate_id and not args.data_file:
        parser.error("one of --candidate-id or --data-file is required (unless using --list-tabs)")

    return args


async def list_tabs(port: int) -> int:
    """List all open browser tabs and their URLs.

    Args:
        port: Browser debugging port.

    Returns:
        Exit code.
    """
    async with BrowserSession(port=port) as session:
        contexts = session._browser.contexts
        if not contexts:
            console.print("[yellow]No browser contexts found.[/]")
            return 0

        table = Table(title="Open Browser Tabs", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title / URL", style="white")
        table.add_column("Status", width=10)

        total = 0
        for ctx_idx, context in enumerate(contexts):
            for page_idx, page in enumerate(context.pages):
                total += 1
                try:
                    title = await page.title()
                except Exception:
                    title = "(no title)"
                url = page.url
                status = "[green]active[/]" if (ctx_idx == 0 and page_idx == len(context.pages) - 1) else ""
                table.add_row(str(total), f"[bold]{title}[/]\n{url}", status)

        console.print(table)
        console.print(f"\n[dim]Total tabs: {total}. The script uses the last (active) tab.[/]")
    return 0


def show_dry_run(candidate, platform_name: str = "Unknown") -> None:
    """Display a rich preview table of what WOULD be filled.

    Args:
        candidate: CandidateData to preview.
        platform_name: ATS platform name if known.
    """
    console.print()
    console.print(Panel(f"[bold yellow]DRY RUN PREVIEW - {platform_name}[/]\nNo browser interaction will occur.", border_style="yellow"))

    table = Table(title="Fields That Would Be Filled", show_header=True, header_style="bold")
    table.add_column("Field", style="cyan", width=25)
    table.add_column("Value", style="white")
    table.add_column("Status", width=12)

    p = candidate.personal
    fields = [
        ("First Name", p.first_name),
        ("Last Name", p.last_name),
        ("Email", p.email),
        ("Phone", p.phone),
        ("Location", p.location),
        ("LinkedIn URL", p.linkedin_url),
        ("GitHub URL", p.github_url),
        ("Website/Portfolio", p.website),
        ("Resume File", candidate.resume_file_path),
        ("Cover Letter", "[auto-generated]" if not candidate.cover_letter and candidate.experience else candidate.cover_letter),
    ]

    if candidate.experience:
        fields.append(("Current Company", candidate.experience[0].company))
        fields.append(("Current Title", candidate.experience[0].title))

    for field_name, value in fields:
        if value:
            display = str(value)
            if len(display) > 60:
                display = display[:57] + "..."
            table.add_row(field_name, display, "[green]FILL[/]")
        else:
            table.add_row(field_name, "[dim]not provided[/]", "[dim]SKIP[/]")

    console.print(table)
    console.print()
    console.print(f"[bold cyan]Skills:[/] {', '.join(candidate.skills) or 'none'}")
    console.print(f"[bold cyan]Experience entries:[/] {len(candidate.experience)}")
    console.print(f"[bold cyan]Education entries:[/] {len(candidate.education)}")
    console.print()
    console.print("[bold yellow]Run without --dry-run to actually fill the form.[/]")


async def take_screenshot(page, prefix: str = "fill") -> Path | None:
    """Take a screenshot of the current browser page.

    Args:
        page: Playwright page object.
        prefix: Filename prefix.

    Returns:
        Path to saved screenshot, or None on failure.
    """
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = screenshots_dir / f"{prefix}_{timestamp}.png"
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info("Screenshot saved: %s", screenshot_path)
        return screenshot_path
    except Exception as exc:
        logger.warning("Could not take screenshot: %s", exc)
        return None


async def run(args: argparse.Namespace) -> int:
    """Main execution flow.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Step 1: Load config
    config = get_config()
    if args.api_url:
        config = Config(
            api_base_url=args.api_url,
            api_token=config.api_token,
            browser_debug_port=args.port or config.browser_debug_port,
            log_level="DEBUG" if args.debug else config.log_level,
        )

    port = args.port or config.browser_debug_port

    # Handle --list-tabs early
    if args.list_tabs:
        return await list_tabs(port)

    # Step 2: Fetch & validate candidate data BEFORE launching browser
    console.print()
    console.print(Panel("[bold blue]Step 1/3: Loading Candidate Data[/]"))

    if args.data_file:
        candidate = load_candidate_from_file(args.data_file)
    else:
        if not config.api_token:
            console.print(
                "[bold red]ERROR:[/] API_TOKEN is not set. "
                "Configure it in your .env file."
            )
            return 1
        candidate = await fetch_candidate_data(args.candidate_id, config)

    console.print(
        f"  Candidate: [bold]{candidate.personal.full_name}[/] "
        f"({candidate.personal.email})"
    )
    console.print(
        f"  Experience: {len(candidate.experience)} entries | "
        f"Education: {len(candidate.education)} entries | "
        f"Skills: {len(candidate.skills)}"
    )

    # Handle --dry-run: show preview without browser
    if args.dry_run:
        show_dry_run(candidate)
        return 0

    # Step 3: Connect to browser
    console.print()
    console.print(Panel("[bold blue]Step 2/3: Connecting to Browser[/]"))

    async with BrowserSession(port=port) as session:
        # Get or navigate to page
        page = await session.get_active_page()
        if args.url:
            logger.info("Navigating to: %s", args.url)
            try:
                await page.goto(args.url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                console.print(
                    f"[bold yellow]Warning:[/] Could not navigate to URL ({e}). "
                    f"Using current page: {page.url}"
                )

        console.print(f"  Active page: [link]{page.url}[/link]")

        # Step 4: Detect ATS & fill
        console.print()
        console.print(Panel("[bold blue]Step 3/3: Filling Application Form[/]"))

        filler = await get_filler(page, candidate)
        result = await filler.fill()

        # Take screenshot if requested
        if args.screenshot:
            screenshot_path = await take_screenshot(page, prefix=result.ats_platform.lower())
            if screenshot_path:
                console.print(f"  [dim]Screenshot: {screenshot_path}[/]")

        # Save JSON session report
        if not args.no_report:
            report_path = save_report(result, candidate)
            console.print(f"  [dim]Session report: {report_path}[/]")

        # Print final summary table
        console.print()
        summary_table = Table(title="Fill Summary", show_header=True, header_style="bold")
        summary_table.add_column("Category", style="cyan", width=20)
        summary_table.add_column("Fields", style="white")
        summary_table.add_column("Count", width=8, justify="right")

        if result.filled_fields:
            summary_table.add_row(
                "[green]Filled[/]",
                ", ".join(result.filled_fields),
                f"[green]{len(result.filled_fields)}[/]",
            )
        if result.failed_fields:
            summary_table.add_row(
                "[red]Failed[/]",
                ", ".join(result.failed_fields),
                f"[red]{len(result.failed_fields)}[/]",
            )
        if result.skipped_fields:
            summary_table.add_row(
                "[dim]Skipped[/]",
                ", ".join(result.skipped_fields),
                f"[dim]{len(result.skipped_fields)}[/]",
            )

        console.print(summary_table)
        console.print()

        border_style = "yellow" if result.has_failures else "green"
        status_text = (
            f"[bold yellow]Completed with {len(result.failed_fields)} field(s) not filled[/]\n"
            if result.has_failures
            else "[bold green]All fields filled successfully![/]\n"
        )
        console.print(
            Panel(
                status_text +
                f"Success rate: [bold]{result.success_rate:.0f}%[/]\n\n"
                "[bold red][!] REVIEW the form carefully and submit MANUALLY.[/]",
                title="Result",
                border_style=border_style,
            )
        )

    return 0


def main() -> None:
    """Entry point."""
    args = parse_args()
    setup_logging(level="DEBUG" if args.debug else "INFO")

    # Print banner
    banner = Text()
    banner.append("\n  ATS Form Filler v2.0\n", style="bold cyan")
    banner.append("  Semi-Automated | Human-Controlled\n", style="dim")
    banner.append("  [!] NEVER auto-submits - Final Review is Always Yours\n", style="bold red")
    console.print(Panel(banner, border_style="cyan"))

    try:
        exit_code = asyncio.run(run(args))
    except ATSFillerError as exc:
        console.print(f"\n[bold red]ERROR:[/] {exc}")
        logger.debug("Full traceback:", exc_info=True)
        exit_code = 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/]")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
