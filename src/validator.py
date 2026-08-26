"""Candidate data validator with completeness scoring.

Validates a candidate JSON file against the Pydantic schema AND
scores completeness — how well-populated the data is for a real
ATS application.

This is DIFFERENT from --dry-run which shows what would be filled.
--validate-only checks DATA QUALITY without any browser interaction.

Use cases:
  - QA before running a batch fill
  - Check output from Saran's resume parser
  - Detect missing fields that will cause skips during fill
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.models import CandidateData

logger = logging.getLogger(__name__)
console = Console(safe_box=True)


class ValidationReport:
    """Completeness and validity report for candidate data."""

    def __init__(
        self,
        file_path: str,
        candidate: CandidateData | None,
        error: str | None,
    ) -> None:
        self.file_path = file_path
        self.candidate = candidate
        self.error = error
        self.field_scores: list[tuple[str, str, str]] = []  # (field, value_preview, status)
        self.completeness_pct: float = 0.0

        if candidate:
            self._score()

    def _score(self) -> None:
        """Score each field for presence and quality."""
        c = self.candidate
        p = c.personal

        # All scoreable fields: (label, value, is_required)
        fields = [
            ("First Name",      p.first_name,                                       True),
            ("Last Name",       p.last_name,                                        True),
            ("Email",           p.email,                                            True),
            ("Phone",           p.phone,                                            False),
            ("LinkedIn URL",    p.linkedin_url,                                     False),
            ("GitHub URL",      p.github_url,                                       False),
            ("Location",        p.location,                                         False),
            ("Website",         p.website,                                          False),
            ("Resume File",     c.resume_file_path,                                 False),
            ("Cover Letter",    c.cover_letter,                                     False),
            ("Work Experience", f"{len(c.experience)} entries" if c.experience else None, False),
            ("Education",       f"{len(c.education)} entries" if c.education else None,   False),
            ("Skills",          f"{len(c.skills)} skills" if c.skills else None,          False),
            ("Certifications",  f"{len(c.certifications)} certs" if c.certifications else None, False),
        ]

        total = len(fields)
        present = 0

        for field_name, value, required in fields:
            has_value = bool(value and str(value).strip())

            if has_value:
                preview = str(value)
                if len(preview) > 40:
                    preview = preview[:37] + "..."
                status = "[green]OK[/]"
                present += 1
            elif required:
                preview = "MISSING"
                status = "[bold red]REQUIRED[/]"
            else:
                preview = "not provided"
                status = "[yellow]EMPTY[/]"

            self.field_scores.append((field_name, preview, status))

        self.completeness_pct = present / total * 100

        # Check resume file actually exists on disk
        if c.resume_file_path:
            resume_path = Path(c.resume_file_path)
            if not resume_path.is_file():
                for i, (name, _, _) in enumerate(self.field_scores):
                    if name == "Resume File":
                        self.field_scores[i] = (
                            name,
                            f"FILE NOT FOUND: {c.resume_file_path}",
                            "[bold red]BROKEN PATH[/]",
                        )
                        # Deduct from completeness
                        self.completeness_pct = max(0, self.completeness_pct - (100 / total))
                        break


def validate_candidate_file(file_path: str) -> ValidationReport:
    """Load and validate a single candidate JSON file.

    Args:
        file_path: Path to the JSON file to validate.

    Returns:
        ValidationReport with scoring details.
    """
    path = Path(file_path)

    if not path.is_file():
        return ValidationReport(
            file_path=file_path,
            candidate=None,
            error=f"File not found: {file_path}",
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ValidationReport(
            file_path=file_path,
            candidate=None,
            error=f"Invalid JSON: {exc}",
        )

    try:
        candidate = CandidateData(**raw)
        return ValidationReport(file_path=file_path, candidate=candidate, error=None)
    except ValidationError as exc:
        errors = "; ".join(
            f"{' -> '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        return ValidationReport(
            file_path=file_path,
            candidate=None,
            error=f"Schema validation failed: {errors}",
        )


def validate_batch_directory(dir_path: str) -> list[ValidationReport]:
    """Validate all JSON files in a directory.

    Args:
        dir_path: Path to directory containing candidate JSON files.

    Returns:
        List of ValidationReport, one per file.
    """
    reports = []
    for json_file in sorted(Path(dir_path).glob("*.json")):
        reports.append(validate_candidate_file(str(json_file)))
    return reports


def print_validation_report(report: ValidationReport) -> None:
    """Print a rich validation report for a single candidate file."""
    path_name = Path(report.file_path).name

    if report.error:
        console.print(Panel(
            f"[bold red]INVALID:[/] {report.error}\n[dim]File: {report.file_path}[/]",
            title=f"[red]Validation Failed -- {path_name}[/]",
            border_style="red",
        ))
        return

    c = report.candidate
    pct = report.completeness_pct
    color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
    grade = (
        "EXCELLENT" if pct >= 90 else
        "GOOD" if pct >= 70 else
        "FAIR" if pct >= 50 else
        "POOR"
    )

    console.print(Panel(
        f"[bold green]VALID[/] -- {c.personal.full_name} ({c.personal.email})\n"
        f"Completeness: [{color}]{pct:.0f}%[/] -- [{color}]{grade}[/]\n"
        f"[dim]File: {report.file_path}[/]",
        title=f"[bold]Validation Report -- {path_name}[/]",
        border_style=color,
    ))

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Field", style="cyan", width=22)
    table.add_column("Value Preview", width=42)
    table.add_column("Status", width=20)

    for field_name, preview, status in report.field_scores:
        table.add_row(field_name, preview, status)

    console.print(table)
    console.print()


def print_batch_validation_summary(reports: list[ValidationReport]) -> None:
    """Print a summary table for batch validation results."""
    total = len(reports)
    valid = sum(1 for r in reports if r.candidate is not None)
    invalid = total - valid

    table = Table(
        title=f"Batch Validation -- {valid}/{total} valid",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("File", width=30)
    table.add_column("Candidate", width=22)
    table.add_column("Status", width=12)
    table.add_column("Completeness", width=14, justify="right")

    for i, report in enumerate(reports, 1):
        path_name = Path(report.file_path).name
        if report.candidate:
            pct = report.completeness_pct
            color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
            table.add_row(
                str(i),
                path_name,
                report.candidate.personal.full_name,
                "[green]VALID[/]",
                f"[{color}]{pct:.0f}%[/]",
            )
        else:
            short_err = (report.error or "")[:25]
            table.add_row(str(i), path_name, "--", "[red]INVALID[/]", f"[red]{short_err}[/]")

    console.print(table)
    console.print(f"\n[bold]Summary:[/] {valid} valid, {invalid} invalid out of {total} files")
