"""Unit tests for the validator and health check modules."""

import json
import tempfile
from pathlib import Path
import pytest
from playwright.async_api import async_playwright

from src.validator import (
    validate_candidate_file,
    validate_batch_directory,
)
from src.health_check import check_selector, run_health_check
from src.exporter import generate_html_dashboard


def test_validate_valid_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        data = {
            "personal": {
                "first_name": "Tamish",
                "last_name": "Sridatta",
                "email": "tamish@example.com",
                "phone": "+91-9876543210",
            },
            "experience": [],
            "education": [],
            "skills": ["Python", "Playwright"],
        }
        f.write(json.dumps(data))
        file_path = f.name

    try:
        report = validate_candidate_file(file_path)
        assert report.candidate is not None
        assert report.error is None
        assert report.completeness_pct > 0
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_validate_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("NOT JSON CONTENT")
        file_path = f.name

    try:
        report = validate_candidate_file(file_path)
        assert report.candidate is None
        assert "Invalid JSON" in report.error
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_validate_missing_required_fields():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        data = {
            "personal": {
                "last_name": "Sridatta",
                # missing first_name and email
            }
        }
        f.write(json.dumps(data))
        file_path = f.name

    try:
        report = validate_candidate_file(file_path)
        assert report.candidate is None
        assert "Schema validation failed" in report.error
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_validate_broken_resume_path():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        data = {
            "personal": {
                "first_name": "Tamish",
                "last_name": "Sridatta",
                "email": "tamish@example.com",
            },
            "resume_file_path": "c:/non_existent_path/fake_resume.pdf"
        }
        f.write(json.dumps(data))
        file_path = f.name

    try:
        report = validate_candidate_file(file_path)
        assert report.candidate is not None
        # Check that broken resume path was flagged in scores
        resume_score = next(s for s in report.field_scores if s[0] == "Resume File")
        assert "BROKEN PATH" in resume_score[2]
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_exporter_generates_valid_html():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_html = Path(tmp_dir) / "test_dashboard.html"
        generated = generate_html_dashboard(output_path=out_html)
        assert generated.exists()
        content = generated.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "ATS Form Filler" in content
        assert "Application Pipeline" in content


@pytest.mark.asyncio
async def test_health_check_detects_present_selectors():
    html = """
    <html>
    <body>
        <input id="first_name" type="text" />
        <input id="last_name" type="text" />
        <input id="email" type="email" />
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        found, count = await check_selector(page, "#first_name")
        assert found is True
        assert count == 1

        not_found, count2 = await check_selector(page, "#non_existent_element")
        assert not_found is False
        assert count2 == 0

        reports = await run_health_check(page)
        assert len(reports) == 4  # Greenhouse, Lever, Workday, SmartRecruiters
        # Greenhouse should have found first_name and last_name and email
        gh_report = next(r for r in reports if r.platform_name == "Greenhouse")
        assert gh_report.found_count >= 3
        assert gh_report.coverage_pct > 0

        await browser.close()
