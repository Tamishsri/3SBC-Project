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

# Add project root to sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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
        help="Path to a local JSON file with candidate data",
    )
    data_group.add_argument(
        "--batch-dir",
        type=str,
        help="Directory of candidate JSON files to process sequentially (batch mode)",
    )

    parser.add_argument(
        "--batch-delay",
        type=float,
        default=5.0,
        help="Seconds to wait between candidates in batch mode (default: 5, for rate limiting)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent workers for parallel batch processing (default: 1, max recommended: 5)",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="default",
        help="User or process identifier for multi-user / multi-tenant tracking (default: 'default')",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and score candidate JSON data quality without touching the browser",
    )
    parser.add_argument(
        "--check-selectors",
        action="store_true",
        help="Health check: scan the browser page for all known ATS selectors without filling",
    )
    parser.add_argument(
        "--show-tracker",
        action="store_true",
        help="Display the application pipeline tracker (job-level history) and exit",
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
        "--human-mode",
        action="store_true",
        help="Type fields character-by-character to simulate human input (slower, avoids bot detection)",
    )
    parser.add_argument(
        "--show-reports",
        action="store_true",
        help="Display past fill session reports and exit",
    )
    parser.add_argument(
        "--multi-page",
        action="store_true",
        help="Auto-advance through multi-page wizard steps (Workday/SmartRecruiters) up to the final review screen",
    )
    parser.add_argument(
        "--verify-contract",
        type=str,
        default=None,
        help="Verify a JSON file from teammate Saran's resume parser against the CandidateData contract",
    )
    parser.add_argument(
        "--export-dashboard",
        action="store_true",
        help="Export all tracked applications to a visual, standalone HTML dashboard file",
    )
    parser.add_argument(
        "--serve-dashboard",
        action="store_true",
        help="Launch the interactive live dashboard HTTP server with real-time analytics polling",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8080,
        help="Port for live dashboard server (default: 8080)",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help="HTTP(S) webhook URL (Slack, Discord, Zapier) for real-time application staging alerts",
    )
    parser.add_argument(
        "--save-preset",
        type=str,
        default=None,
        help="Save preferences from --data-file as a named preset (e.g. 'default_us')",
    )
    parser.add_argument(
        "--use-preset",
        type=str,
        default=None,
        help="Load and merge a named preference preset with the candidate data",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List all saved preference presets and exit",
    )
    parser.add_argument(
        "--parse-resume",
        type=str,
        default=None,
        help="Extract candidate data directly from a local .pdf or .txt resume file",
    )
    parser.add_argument(
        "--allow-generic",
        action="store_true",
        help="Enable adaptive generic web form filler fallback for unlisted ATS platforms & custom job portals",
    )
    parser.add_argument(
        "--detect-captcha",
        action="store_true",
        help="Scan page for Cloudflare Turnstile, reCAPTCHA, and bot challenges with human intervention pause",
    )
    parser.add_argument(
        "--generate-cover-letter",
        action="store_true",
        help="Synthesize a tailored contextual cover letter from active page company & role metadata",
    )
    parser.add_argument(
        "--resume-batch",
        action="store_true",
        help="Resume interrupted batch processing from the last saved recovery checkpoint",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s v2.6 | ATS Form Filler | Semi-Automated | Never auto-submits",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    # Validate: some source of work is required
    no_work_mode = (
        not args.list_tabs
        and not args.show_reports
        and not args.show_tracker
        and not args.export_dashboard
        and not args.serve_dashboard
        and not args.list_presets
        and not args.save_preset
        and not args.parse_resume
        and not args.check_selectors
        and not args.verify_contract
        and not args.candidate_id
        and not args.data_file
        and not args.batch_dir
    )
    if no_work_mode:
        parser.error(
            "specify one of: --candidate-id, --data-file, --batch-dir, "
            "--list-tabs, --show-reports, --show-tracker, --export-dashboard, "
            "--serve-dashboard, --list-presets, --save-preset, --parse-resume, "
            "--verify-contract, or --check-selectors"
        )

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


def show_reports() -> int:
    """Display past fill session reports from fill_reports/ in a rich table.

    Returns:
        Exit code.
    """
    reports_dir = Path("fill_reports")
    if not reports_dir.exists() or not list(reports_dir.glob("*.json")):
        console.print("[yellow]No session reports found. Run a fill to generate reports.[/]")
        console.print(f"[dim]Reports are saved to: {reports_dir.resolve()}[/]")
        return 0

    report_files = sorted(reports_dir.glob("*.json"), reverse=True)

    table = Table(
        title=f"Fill Session Reports ({len(report_files)} found)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Timestamp", style="dim", width=20)
    table.add_column("Platform", width=16)
    table.add_column("Candidate", style="white", width=22)
    table.add_column("Filled", justify="right", width=8)
    table.add_column("Failed", justify="right", width=8)
    table.add_column("Rate", justify="right", width=8)

    for rp in report_files[:20]:  # show last 20
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
            ts = data.get("timestamp", "")[:19].replace("T", " ")
            platform = data.get("ats_platform", "?")
            candidate = data.get("candidate", {}).get("full_name", "?")
            summary = data.get("summary", {})
            filled = summary.get("filled_count", 0)
            failed = summary.get("failed_count", 0)
            rate = summary.get("success_rate_pct", 0)

            rate_str = f"[green]{rate:.0f}%[/]" if rate == 100 else (
                f"[yellow]{rate:.0f}%[/]" if rate >= 70 else f"[red]{rate:.0f}%[/]"
            )
            failed_str = f"[red]{failed}[/]" if failed > 0 else f"[dim]{failed}[/]"

            table.add_row(ts, platform, candidate, str(filled), failed_str, rate_str)
        except Exception:
            continue

    console.print(table)
    console.print(f"\n[dim]Reports stored in: {reports_dir.resolve()}[/]")
    return 0


def show_tracker() -> int:
    """Display the job-level application pipeline tracker from application_log.csv."""
    from src.tracker import load_tracker, _DEFAULT_LOG_PATH

    entries = load_tracker()
    if not entries:
        console.print("[yellow]No applications tracked yet. Run a fill to start tracking.[/]")
        console.print(f"[dim]Tracker CSV: {_DEFAULT_LOG_PATH.resolve()}[/]")
        return 0

    table = Table(
        title=f"Application Pipeline ({len(entries)} applications)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Date", style="dim", width=18)
    table.add_column("Candidate", width=20)
    table.add_column("Company", width=18)
    table.add_column("ATS", width=16)
    table.add_column("Rate", width=8, justify="right")
    table.add_column("F/F/S", width=10, justify="right")

    for entry in reversed(entries[-30:]):  # last 30, newest first
        rate = float(entry.get("success_rate_pct", 0))
        color = "green" if rate >= 90 else ("yellow" if rate >= 60 else "red")
        filled = entry.get("fields_filled", "?")
        failed = entry.get("fields_failed", "?")
        skipped = entry.get("fields_skipped", "?")
        table.add_row(
            entry.get("timestamp", "")[:16],
            entry.get("candidate_name", "?"),
            entry.get("company_guess", "?"),
            entry.get("ats_platform", "?"),
            f"[{color}]{rate:.0f}%[/]",
            f"{filled}/{failed}/{skipped}",
        )

    console.print(table)
    console.print("[dim]Columns: Filled/Failed/Skipped[/]")
    console.print(f"[dim]Tracker: {_DEFAULT_LOG_PATH.resolve()}[/]")
    return 0


def run_validate_only(args: argparse.Namespace) -> int:
    """Validate candidate JSON file(s) for schema correctness and completeness."""
    from src.validator import (
        validate_candidate_file,
        validate_batch_directory,
        print_validation_report,
        print_batch_validation_summary,
    )

    if args.data_file:
        report = validate_candidate_file(args.data_file)
        print_validation_report(report)
        return 0 if report.candidate is not None else 1

    if args.batch_dir:
        from pathlib import Path as _Path
        reports = validate_batch_directory(args.batch_dir)
        if not reports:
            console.print(f"[yellow]No JSON files found in: {args.batch_dir}[/]")
            return 1
        for report in reports:
            print_validation_report(report)
        print_batch_validation_summary(reports)
        invalid_count = sum(1 for r in reports if r.candidate is None)
        return 1 if invalid_count > 0 else 0

    console.print("[red]--validate-only requires --data-file or --batch-dir[/]")
    return 1


async def run_batch_mode(args: argparse.Namespace, port: int) -> int:
    """Run batch processing across all JSONs in --batch-dir."""
    from pathlib import Path as _Path

    batch_dir = _Path(args.batch_dir)
    if not batch_dir.is_dir():
        console.print(f"[red]ERROR:[/] --batch-dir is not a directory: {args.batch_dir}")
        return 1

    if args.concurrency > 1:
        from src.worker_pool import ConcurrentWorkerPool, TaskItem
        json_files = sorted(batch_dir.glob("*.json"))
        if not json_files:
            console.print(f"[yellow]No JSON files found in: {batch_dir}[/]")
            return 0

        tasks = [
            TaskItem(
                task_id=f"{i+1:03d}_{f.stem}",
                data_file=f,
                job_url=args.url,
                user_id=args.user_id,
                human_mode=args.human_mode,
                multi_page=args.multi_page,
                screenshot=args.screenshot,
                webhook_url=args.webhook_url,
                preset=args.use_preset,
                allow_generic=args.allow_generic,
                detect_captcha=args.detect_captcha,
                generate_cover_letter=args.generate_cover_letter,
            )
            for i, f in enumerate(json_files)
        ]

        pool = ConcurrentWorkerPool(max_concurrency=args.concurrency, port=port)
        outcomes = await pool.run_tasks(tasks)
        failed = sum(1 for o in outcomes if not o.success)
        return 1 if failed > 0 else 0
    else:
        from src.batch import run_batch
        results = await run_batch(
            batch_dir=batch_dir,
            port=port,
            url=args.url,
            human_mode=args.human_mode,
            multi_page=args.multi_page,
            screenshot=args.screenshot,
            delay_seconds=args.batch_delay,
            webhook_url=args.webhook_url,
            preset=args.use_preset,
            allow_generic=args.allow_generic,
            detect_captcha=args.detect_captcha,
            generate_cover_letter=args.generate_cover_letter,
            resume=args.resume_batch,
        )
        failed = sum(1 for r in results if not r.success)
        return 1 if failed > 0 else 0


async def run_check_selectors(port: int, args: argparse.Namespace) -> int:
    """Run ATS form health check on the current browser page."""
    from src.health_check import run_health_check, print_health_report

    console.print()
    console.print(Panel(
        "[bold cyan]ATS Selector Health Check[/]\n"
        "Scanning page for all known selectors across all platforms...\n"
        "[dim]No fields will be filled. Read-only inspection.[/]",
    ))

    try:
        async with BrowserSession(port=port) as session:
            page = await session.get_active_page()
            if args.url:
                await page.goto(args.url, wait_until="domcontentloaded", timeout=15000)
            reports = await run_health_check(page)
            print_health_report(reports)
        return 0
    except Exception as exc:
        console.print(f"[red]Health check failed:[/] {exc}")
        return 1


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

    # Handle --show-reports early
    if args.show_reports:
        return show_reports()

    # Handle --show-tracker early
    if args.show_tracker:
        return show_tracker()

    # Handle --serve-dashboard early
    if args.serve_dashboard:
        from src.server import run_server
        port_num = args.dashboard_port or 8080
        console.print(f"[bold cyan]Starting Live Dashboard Server on http://127.0.0.1:{port_num}/ ...[/]")
        console.print("[dim]Serving dynamic live application stats. Press Ctrl+C to stop.[/]")
        run_server(port=port_num, open_browser=True, block=True)
        return 0

    # Handle --list-presets early
    if args.list_presets:
        from src.presets import list_presets
        presets = list_presets()
        if not presets:
            console.print("[yellow]No presets found. Use --save-preset <name> --data-file <file> to create one.[/]")
        else:
            console.print(f"[bold cyan]Available Preference Presets ({len(presets)} found):[/]")
            for p in presets:
                console.print(f"  • [bold green]{p}[/]")
        return 0

    # Handle --save-preset early
    if args.save_preset:
        if not args.data_file:
            console.print("[red]ERROR:[/] --save-preset requires --data-file containing the preference template.")
            return 1
        from src.presets import save_preset
        raw_data = json.loads(Path(args.data_file).read_text(encoding="utf-8"))
        preset_file = save_preset(args.save_preset, raw_data)
        console.print(f"[bold green]Preset saved successfully![/] Saved to: {preset_file}")
        return 0

    # Handle --parse-resume early
    if args.parse_resume:
        from src.resume_fallback import parse_and_save_candidate, parse_resume_file
        try:
            cand = parse_resume_file(args.parse_resume)
            out_file = parse_and_save_candidate(args.parse_resume)
            console.print(f"[bold green]Resume parsed successfully![/]")
            console.print(f"  • Candidate: [bold]{cand.personal.full_name}[/] ({cand.personal.email})")
            console.print(f"  • Phone: {cand.personal.phone or 'N/A'}")
            console.print(f"  • Location: {cand.personal.location or 'N/A'}")
            console.print(f"  • Skills: {', '.join(cand.skills[:8])}...")
            console.print(f"  • Saved schema JSON: [dim]{out_file.resolve()}[/]")
            return 0
        except Exception as exc:
            console.print(f"[bold red]Resume parsing error:[/] {exc}")
            return 1

    # Handle --export-dashboard early
    if args.export_dashboard:
        from src.exporter import generate_html_dashboard
        dashboard_path = generate_html_dashboard()
        console.print(f"[bold green]Dashboard generated successfully![/]")
        console.print(f"[dim]Saved to: {dashboard_path.resolve()}[/]")
        return 0

    # Handle --verify-contract early
    if args.verify_contract:
        from src.contract_verifier import verify_parser_file, print_contract_diagnostic
        diagnostic = verify_parser_file(args.verify_contract)
        print_contract_diagnostic(diagnostic)
        return 0 if diagnostic.is_valid else 1

    # Handle --validate-only (no browser needed)
    if args.validate_only:
        return run_validate_only(args)

    # Handle --batch-dir (batch processing mode)
    if args.batch_dir:
        return await run_batch_mode(args, port)

    # Handle --check-selectors (browser needed, but no filling)
    if args.check_selectors:
        return await run_check_selectors(port, args)

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

    if args.use_preset:
        from src.presets import merge_candidate_with_preset
        candidate = merge_candidate_with_preset(candidate, args.use_preset)
        console.print(f"  [dim]Applied preference preset: [bold]{args.use_preset}[/][/]")

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

        if args.detect_captcha:
            from src.captcha_detector import handle_captcha_challenge
            await handle_captcha_challenge(page)

        if args.generate_cover_letter:
            from src.cover_letter_generator import augment_candidate_cover_letter
            candidate = await augment_candidate_cover_letter(candidate, page)

        if args.human_mode:
            console.print("  [dim][bold]Human Mode ON[/] - typing character-by-character (slower but safer)[/]")
        if args.multi_page:
            console.print("  [dim][bold]Multi-Page Mode ON[/] - auto-advancing through wizard steps up to review page[/]")
        if args.allow_generic:
            console.print("  [dim][bold]Generic Fallback ON[/] - enabled adaptive web form engine for unlisted ATS pages[/]")

        filler = await get_filler(
            page,
            candidate,
            human_mode=args.human_mode,
            multi_page=args.multi_page,
            allow_generic=args.allow_generic,
        )
        result = await filler.fill()

        # Take screenshot if requested
        if args.screenshot:
            screenshot_path = await take_screenshot(page, prefix=result.ats_platform.lower().replace(" ", "_"))
            if screenshot_path:
                console.print(f"  [dim]Screenshot: {screenshot_path}[/]")

        # Save JSON session report
        if not args.no_report:
            report_path = save_report(result, candidate)
            console.print(f"  [dim]Session report: {report_path}[/]")

        # Log application to pipeline tracker CSV
        from src.tracker import append_to_tracker
        source_path = Path(args.data_file) if args.data_file else None
        tracker_path = append_to_tracker(result, candidate, source_file=source_path)
        console.print(f"  [dim]Pipeline tracker updated: {tracker_path}[/]")

        # Send webhook notification if specified
        if args.webhook_url:
            from src.notifier import send_fill_notification
            await send_fill_notification(args.webhook_url, result, candidate)
            console.print(f"  [dim]Webhook notification sent: {args.webhook_url}[/]")

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
    banner.append("\n  ATS Form Filler v2.6\n", style="bold cyan")
    banner.append("  Semi-Automated | Human-Controlled | Multi-Page & Adaptive Web Intelligence\n", style="dim")
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
