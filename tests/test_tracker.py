"""Unit tests for the application tracker (job pipeline log)."""

import tempfile
from pathlib import Path
import pytest

from src.models import CandidateData, PersonalInfo, FillResult
from src.tracker import append_to_tracker, load_tracker, _guess_company


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+91-9876543210",
        )
    )


@pytest.fixture
def sample_fill_result():
    return FillResult(
        ats_platform="Greenhouse",
        page_url="https://boards.greenhouse.io/stripe/jobs/12345",
        filled_fields=["First Name", "Last Name", "Email"],
        failed_fields=[],
        skipped_fields=["LinkedIn"],
    )


def test_guess_company():
    assert _guess_company("https://boards.greenhouse.io/stripe/jobs/123") == "Stripe"
    assert _guess_company("https://jobs.lever.co/netflix/abc-123") == "Netflix"
    assert _guess_company("https://careers.smartrecruiters.com/Spotify/job1") == "Spotify"
    assert _guess_company("https://uber.wd3.myworkdayjobs.com/careers/job") == "Uber"


def test_append_and_load_tracker(sample_candidate, sample_fill_result):
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "test_app_log.csv"

        # Append first entry
        append_to_tracker(sample_fill_result, sample_candidate, log_path=csv_path)
        assert csv_path.exists()

        entries = load_tracker(log_path=csv_path)
        assert len(entries) == 1
        assert entries[0]["candidate_name"] == "Tamish Sridatta"
        assert entries[0]["ats_platform"] == "Greenhouse"
        assert entries[0]["company_guess"] == "Stripe"
        assert entries[0]["success_rate_pct"] == "100.0"

        # Append second entry
        second_result = FillResult(
            ats_platform="Lever",
            page_url="https://jobs.lever.co/figma/designer",
            filled_fields=["Full Name"],
            failed_fields=["Resume"],
        )
        append_to_tracker(second_result, sample_candidate, log_path=csv_path)

        entries = load_tracker(log_path=csv_path)
        assert len(entries) == 2
        assert entries[1]["company_guess"] == "Figma"
        assert entries[1]["ats_platform"] == "Lever"
