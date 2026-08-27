"""Application tracker — job pipeline CSV log.

Tracks every job application at the JOB level (not field level).
Writes a running application_log.csv so candidates and recruiters can
see the full job search pipeline: what was applied, when, and with what result.

This is DIFFERENT from fill_reports/ which logs field-level fill details.
The tracker provides a job-search pipeline overview.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from src.file_lock import FileLock
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path("application_log.csv")

# CSV columns
_COLUMNS = [
    "timestamp",
    "candidate_name",
    "candidate_email",
    "ats_platform",
    "job_url",
    "company_guess",
    "fields_filled",
    "fields_failed",
    "fields_skipped",
    "success_rate_pct",
    "source_file",
    "notes",
]


def _guess_company(url: str) -> str:
    """Try to extract a company name from a job URL."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path or ""

        # Greenhouse: boards.greenhouse.io/COMPANY/jobs/...
        if "greenhouse.io" in host:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].replace("-", " ").title()

        # Lever: jobs.lever.co/COMPANY/...
        if "lever.co" in host:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].replace("-", " ").title()

        # SmartRecruiters: careers.smartrecruiters.com/COMPANY/...
        if "smartrecruiters.com" in host:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].replace("-", " ").title()

        # Workday: company.wd3.myworkdayjobs.com
        if "myworkdayjobs.com" in host:
            subdomain = host.split(".")[0]
            return subdomain.replace("-", " ").title()

        return host
    except Exception:
        return "Unknown"


def append_to_tracker(
    result: FillResult,
    candidate: CandidateData,
    source_file: Path | None = None,
    notes: str = "",
    log_path: Path | None = None,
) -> Path:
    """Append a job application entry to the tracker CSV in a process-safe manner.

    Uses FileLock to prevent race conditions and file corruption when multiple
    users or worker processes write concurrently.

    Args:
        result: FillResult from the fill operation.
        candidate: CandidateData used during the fill.
        source_file: Optional path to the source JSON file.
        notes: Optional free-text notes to attach to this entry.
        log_path: Path to write the CSV (default: application_log.csv).

    Returns:
        Path to the tracker CSV file.
    """
    log_path = log_path or _DEFAULT_LOG_PATH

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_name": candidate.personal.full_name,
        "candidate_email": candidate.personal.email,
        "ats_platform": result.ats_platform,
        "job_url": result.page_url,
        "company_guess": _guess_company(result.page_url),
        "fields_filled": len(result.filled_fields),
        "fields_failed": len(result.failed_fields),
        "fields_skipped": len(result.skipped_fields),
        "success_rate_pct": f"{result.success_rate:.1f}",
        "source_file": str(source_file) if source_file else "",
        "notes": notes,
    }

    with FileLock(log_path):
        write_header = not log_path.exists() or log_path.stat().st_size == 0
        with log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    logger.info("[TRACKER] Entry logged to: %s", log_path)
    return log_path


def load_tracker(log_path: Path | None = None) -> list[dict]:
    """Load all entries from the application tracker CSV in a thread-safe manner.

    Args:
        log_path: Path to the tracker CSV (default: application_log.csv).

    Returns:
        List of row dicts, or empty list if file doesn't exist.
    """
    log_path = log_path or _DEFAULT_LOG_PATH
    if not log_path.exists():
        return []

    with FileLock(log_path):
        with log_path.open("r", encoding="utf-8") as f:
            return list(csv.DictReader(f))


# Public export for context generators and diagnostics
guess_company = _guess_company
