"""ATS form selector health checker.

Scans an open browser page for all known selectors across all registered
ATS platforms. Reports which selectors are present, which are missing,
and makes a confidence assessment of whether a filler will succeed.

This is a DIAGNOSTIC tool — it does NOT fill anything. Use it to:
  - Detect when an ATS has changed its UI (selector drift)
  - Debug why fields are failing on a specific job page
  - Verify selector coverage before a real fill run
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from playwright.async_api import Page
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.fillers.greenhouse import GreenhouseFiller
from src.fillers.lever import LeverFiller
from src.fillers.workday import WorkdayFiller
from src.fillers.smartrecruiters import SmartRecruitersFiller

logger = logging.getLogger(__name__)
console = Console(safe_box=True)

# All fillers to check
_FILLER_CLASSES = [GreenhouseFiller, LeverFiller, WorkdayFiller, SmartRecruitersFiller]


@dataclass
class SelectorResult:
    """Result for a single selector check."""
    field_name: str
    selector: str
    found: bool
    element_count: int = 0


@dataclass
class PlatformHealthReport:
    """Health report for a single ATS platform."""
    platform_name: str
    page_url: str
    field_results: list[SelectorResult] = field(default_factory=list)

    @property
    def found_count(self) -> int:
        # Count fields with at least one matching selector
        found_fields = {r.field_name for r in self.field_results if r.found}
        return len(found_fields)

    @property
    def total_fields(self) -> int:
        all_fields = {r.field_name for r in self.field_results}
        return len(all_fields)

    @property
    def coverage_pct(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return self.found_count / self.total_fields * 100

    @property
    def confidence(self) -> str:
        pct = self.coverage_pct
        if pct >= 80:
            return "HIGH"
        elif pct >= 50:
            return "MEDIUM"
        elif pct >= 20:
            return "LOW"
        return "NONE"


async def check_selector(page: Page, selector: str) -> tuple[bool, int]:
    """Check if a selector matches any elements on the current page.

    Args:
        page: Playwright page to check.
        selector: CSS/Playwright selector string.

    Returns:
        Tuple of (found: bool, count: int).
    """
    try:
        locator = page.locator(selector)
        count = await locator.count()
        return count > 0, count
    except Exception:
        return False, 0


async def run_health_check(page: Page) -> list[PlatformHealthReport]:
    """Run a full selector health check against the current page.

    Checks all known selectors for all registered ATS platforms.
    Does NOT interact with or modify the page in any way.

    Args:
        page: Playwright page to inspect.

    Returns:
        List of PlatformHealthReport, one per platform.
    """
    reports = []

    for filler_cls in _FILLER_CLASSES:
        report = PlatformHealthReport(
            platform_name=filler_cls.platform_name,
            page_url=page.url,
        )

        selectors_dict = getattr(filler_cls, "SELECTORS", {})

        for field_name, selector_list in selectors_dict.items():
            field_found = False
            for selector in selector_list:
                found, count = await check_selector(page, selector)
                report.field_results.append(SelectorResult(
                    field_name=field_name,
                    selector=selector,
                    found=found,
                    element_count=count,
                ))
                if found:
                    field_found = True
                    break  # Found at least one selector for this field

        reports.append(report)

    return reports


def print_health_report(reports: list[PlatformHealthReport], verbose: bool = False) -> None:
    """Print health check results as rich tables.

    Args:
        reports: List of PlatformHealthReport from run_health_check().
        verbose: If True, show ALL selectors tried. Default shows only field-level.
    """
    # Find best-matching platform
    best = max(reports, key=lambda r: r.coverage_pct)

    console.print()
    console.print(Panel(
        f"[bold]Best match:[/] [cyan]{best.platform_name}[/] "
        f"({best.coverage_pct:.0f}% selector coverage, confidence: [bold]{best.confidence}[/])\n"
        f"[dim]Page: {best.page_url}[/]",
        title="[bold]ATS Form Health Check",
        border_style="cyan",
    ))

    for report in sorted(reports, key=lambda r: r.coverage_pct, reverse=True):
        # Aggregate to field level
        fields: dict[str, bool] = {}
        for result in report.field_results:
            if result.field_name not in fields:
                fields[result.field_name] = result.found
            elif result.found:
                fields[result.field_name] = True

        conf_color = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red", "NONE": "dim"}.get(
            report.confidence, "white"
        )

        table = Table(
            title=f"{report.platform_name} — {report.coverage_pct:.0f}% coverage",
            show_header=True,
            header_style="bold",
            border_style=conf_color,
        )
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Status", width=12)
        table.add_column("Selectors Found", style="dim")

        for field_name, found in fields.items():
            # Get first found selector for display
            found_selectors = [
                r.selector for r in report.field_results
                if r.field_name == field_name and r.found
            ]
            selector_display = found_selectors[0] if found_selectors else "none"
            status = "[green]FOUND[/]" if found else "[red]MISSING[/]"
            table.add_row(field_name, status, selector_display)

        console.print(table)
        console.print()
