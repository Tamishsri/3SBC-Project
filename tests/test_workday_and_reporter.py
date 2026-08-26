"""Integration tests for Workday filler and session reporter."""

import json
import tempfile
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from src.models import CandidateData, PersonalInfo, WorkExperience, FillResult
from src.fillers.workday import WorkdayFiller
from src.reporter import save_report


@pytest.fixture
def candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+91-9876543210",
            linkedin_url="https://linkedin.com/in/tamishsri",
            github_url="https://github.com/Tamishsri",
            location="Chennai, India",
            website="https://tamishsri.dev",
        ),
        experience=[
            WorkExperience(
                company="3SBC Tech",
                title="Software Engineer",
                start_date="2024-01",
            )
        ],
        skills=["Python", "Playwright", "FastAPI"],
        cover_letter="I am excited to apply for this position.",
    )


@pytest.mark.asyncio
async def test_workday_filler_execution_flow(candidate):
    """Test WorkdayFiller fills fields correctly on a Workday-like HTML DOM."""
    workday_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Workday Job Application</title></head>
    <body>
        <form id="wd-form">
            <input data-automation-id="legalNameSection_firstName" type="text" />
            <input data-automation-id="legalNameSection_lastName" type="text" />
            <input data-automation-id="email" type="email" />
            <input data-automation-id="phone-number" type="tel" />
        </form>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(workday_html)

        filler = WorkdayFiller(page, candidate)
        result = await filler.fill()

        assert result.ats_platform == "Workday"
        assert "First Name" in result.filled_fields
        assert "Last Name" in result.filled_fields
        assert "Email" in result.filled_fields
        assert "Phone" in result.filled_fields

        # Verify DOM values
        assert await page.input_value('[data-automation-id="legalNameSection_firstName"]') == "Tamish"
        assert await page.input_value('[data-automation-id="legalNameSection_lastName"]') == "Sridatta"
        assert await page.input_value('[data-automation-id="email"]') == "tamish@example.com"

        await browser.close()


@pytest.mark.asyncio
async def test_greenhouse_cover_letter(candidate):
    """Test GreenhouseFiller fills cover letter textarea."""
    from src.fillers.greenhouse import GreenhouseFiller

    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Greenhouse Application</title></head>
    <body>
        <form id="application_form">
            <input type="text" id="first_name" name="job_application[first_name]" />
            <input type="text" id="last_name" name="job_application[last_name]" />
            <input type="email" id="email" name="job_application[email]" />
            <input type="tel" id="phone" name="job_application[phone]" />
            <textarea id="cover_letter_text" name="cover_letter_text"></textarea>
        </form>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = GreenhouseFiller(page, candidate)
        result = await filler.fill()

        # Cover letter from candidate.cover_letter should be filled
        assert "Cover Letter" in result.filled_fields
        val = await page.input_value("#cover_letter_text")
        assert "excited to apply" in val

        await browser.close()


def test_reporter_saves_json(candidate):
    """Test that save_report writes a valid JSON report file."""
    result = FillResult(
        ats_platform="Greenhouse",
        page_url="https://boards.greenhouse.io/company/jobs/123456",
        filled_fields=["First Name", "Last Name", "Email", "Phone", "Cover Letter"],
        failed_fields=["Resume"],
        skipped_fields=["LinkedIn URL"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        report_dir = Path(tmp)
        report_path = save_report(result, candidate, report_dir=report_dir)

        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))

        assert data["schema_version"] == "1.0"
        assert data["ats_platform"] == "Greenhouse"
        assert data["candidate"]["full_name"] == "Tamish Sridatta"
        assert data["summary"]["filled_count"] == 5
        assert data["summary"]["failed_count"] == 1
        assert data["summary"]["skipped_count"] == 1
        assert data["summary"]["success_rate_pct"] == round(5 / 6 * 100, 1)
        assert "First Name" in data["filled_fields"]
        assert "Resume" in data["failed_fields"]
        assert "LinkedIn URL" in data["skipped_fields"]


def test_reporter_filename_format(candidate):
    """Test that the report filename follows the timestamp_platform_name format."""
    result = FillResult(
        ats_platform="Lever",
        page_url="https://jobs.lever.co/company/123",
        filled_fields=["Full Name"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        report_dir = Path(tmp)
        report_path = save_report(result, candidate, report_dir=report_dir)

        filename = report_path.name
        assert filename.endswith(".json")
        assert "lever" in filename
        assert "tamish_sridatta" in filename
