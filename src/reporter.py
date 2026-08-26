"""Session report writer.

Saves a structured JSON report after every fill run.
The report captures: timestamp, ATS platform, page URL, candidate name,
fields filled/failed/skipped, and success rate.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)

# Default location: project_root/fill_reports/
_DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "fill_reports"


def save_report(
    result: FillResult,
    candidate: CandidateData,
    report_dir: Path | None = None,
) -> Path:
    """Save a JSON session report for the fill operation.

    Args:
        result: The FillResult returned by the filler.
        candidate: The CandidateData that was used.
        report_dir: Directory to write reports into. Defaults to fill_reports/.

    Returns:
        Path to the created report file.
    """
    report_dir = report_dir or _DEFAULT_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = candidate.personal.full_name.replace(" ", "_").lower()
    filename = f"{timestamp}_{result.ats_platform.lower()}_{safe_name}.json"
    report_path = report_dir / filename

    report_data = {
        "schema_version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "ats_platform": result.ats_platform,
        "page_url": result.page_url,
        "candidate": {
            "full_name": candidate.personal.full_name,
            "email": candidate.personal.email,
        },
        "summary": {
            "total_attempted": len(result.filled_fields) + len(result.failed_fields),
            "filled_count": len(result.filled_fields),
            "failed_count": len(result.failed_fields),
            "skipped_count": len(result.skipped_fields),
            "success_rate_pct": round(result.success_rate, 1),
            "has_failures": result.has_failures,
        },
        "filled_fields": result.filled_fields,
        "failed_fields": result.failed_fields,
        "skipped_fields": result.skipped_fields,
    }

    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    logger.info("Session report saved: %s", report_path)
    return report_path
