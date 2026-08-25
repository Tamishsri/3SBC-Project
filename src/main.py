"""CLI entry point for the ATS Form Filler.

Orchestrates the entire flow:
1. Parse CLI arguments
2. Load configuration
3. Fetch & validate candidate data (HALT if invalid)
4. Connect to browser via CDP (HALT if connection fails)
5. Detect ATS platform & route to filler
6. Fill the form
7. HALT for human review — NEVER submit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

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
from rich.text import Text

from src.api_client import fetch_candidate_data, load_candidate_from_file
from src.ats_router import get_filler
from src.browser import BrowserSession
from src.config import Config, get_config
from src.exceptions import ATSFillerError

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
    data_group = parser.add_mutually_exclusive_group(required=True)
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
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    """Main execution flow.
    
    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Step 1: Load config
    config = get_config()
    if args.api_url:
        # Override API URL from CLI
        config = Config(
            api_base_url=args.api_url,
            api_token=config.api_token,
            browser_debug_port=args.port or config.browser_debug_port,
            log_level="DEBUG" if args.debug else config.log_level,
        )

    port = args.port or config.browser_debug_port

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
                console.print(f"[bold yellow]Warning:[/] Could not navigate to URL ({e}). Using current page: {page.url}")

        console.print(f"  Active page: [link]{page.url}[/link]")

        # Step 4: Detect ATS & fill
        console.print()
        console.print(Panel("[bold blue]Step 3/3: Filling Application Form[/]"))

        filler = await get_filler(page, candidate)
        result = await filler.fill()

        # Print final summary
        console.print()
        if result.has_failures:
            console.print(
                Panel(
                    f"[bold yellow]⚠️  Completed with {len(result.failed_fields)} "
                    f"field(s) that could not be filled.[/]\n"
                    f"Success rate: {result.success_rate:.0f}%",
                    title="Result",
                    border_style="yellow",
                )
            )
        else:
            console.print(
                Panel(
                    f"[bold green]✅ All fields filled successfully![/]\n"
                    f"Success rate: {result.success_rate:.0f}%",
                    title="Result",
                    border_style="green",
                )
            )

    return 0


def main() -> None:
    """Entry point."""
    args = parse_args()
    setup_logging(level="DEBUG" if args.debug else "INFO")

    # Print banner
    banner = Text()
    banner.append("\n  ATS Form Filler v1.0\n", style="bold cyan")
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
