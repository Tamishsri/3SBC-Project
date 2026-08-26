"""Tests for SmartRecruiters filler, base helpers, and new v2.1 features."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from playwright.async_api import async_playwright

from src.models import CandidateData, PersonalInfo, WorkExperience
from src.fillers.smartrecruiters import SmartRecruitersFiller
from src.fillers.base import ATSFormFiller, is_valid_url
from src.ats_router import get_filler, _FILLER_CLASSES


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
            WorkExperience(company="3SBC Tech", title="Software Engineer", start_date="2024-01")
        ],
        skills=["Python", "Playwright", "FastAPI"],
        cover_letter="I am excited to apply.",
    )


# ── URL Validation ────────────────────────────────────────────────────────────

def test_is_valid_url_valid():
    """Valid URLs should pass."""
    assert is_valid_url("https://linkedin.com/in/test") is True
    assert is_valid_url("https://github.com/user") is True
    assert is_valid_url("http://example.com") is True


def test_is_valid_url_invalid():
    """Invalid/empty URLs should fail."""
    assert is_valid_url(None) is False
    assert is_valid_url("") is False
    assert is_valid_url("not-a-url") is False
    assert is_valid_url("ftp://old-protocol.com") is False


# ── SmartRecruiters Detection ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detect_smartrecruiters(candidate):
    """SmartRecruiters filler detects its URL correctly."""
    mock_page = MagicMock()
    mock_page.url = "https://careers.smartrecruiters.com/Company/apply/job-123"

    filler = await get_filler(mock_page, candidate)
    assert filler.platform_name == "SmartRecruiters"


@pytest.mark.asyncio
async def test_smartrecruiters_not_detected_for_other_urls(candidate):
    """SmartRecruiters should NOT detect Greenhouse URLs."""
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/company/jobs/123"

    filler = await get_filler(mock_page, candidate)
    assert filler.platform_name != "SmartRecruiters"


# ── SmartRecruiters live fill ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smartrecruiters_filler_execution_flow(candidate):
    """SmartRecruiters filler fills fields correctly on mock DOM."""
    sr_html = """
    <!DOCTYPE html>
    <html>
    <head><title>SmartRecruiters Application</title></head>
    <body>
        <form>
            <input data-test-id="first-name" type="text" />
            <input data-test-id="last-name" type="text" />
            <input data-test-id="email" type="email" />
            <input data-test-id="phone" type="tel" />
            <textarea data-test-id="cover-letter"></textarea>
        </form>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(sr_html)

        filler = SmartRecruitersFiller(page, candidate)
        result = await filler.fill()

        assert result.ats_platform == "SmartRecruiters"
        assert "First Name" in result.filled_fields
        assert "Last Name" in result.filled_fields
        assert "Email" in result.filled_fields
        assert "Phone" in result.filled_fields
        assert "Cover Letter" in result.filled_fields

        assert await page.input_value('[data-test-id="first-name"]') == "Tamish"
        assert await page.input_value('[data-test-id="last-name"]') == "Sridatta"
        assert await page.input_value('[data-test-id="email"]') == "tamish@example.com"

        await browser.close()


# ── Human-mode typing ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_mode_fills_correctly(candidate):
    """Human mode should type text correctly even if slower."""
    html = """
    <!DOCTYPE html>
    <html><body>
        <input id="first_name" type="text" />
        <input id="last_name" type="text" />
        <input id="email" type="email" />
        <input id="phone" type="tel" />
    </body></html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        from src.fillers.greenhouse import GreenhouseFiller
        filler = GreenhouseFiller(page, candidate, human_mode=True)

        assert filler.human_mode is True
        # Only test single field to keep test fast
        result = await filler.safe_fill_with_fallbacks(
            [page.locator("#first_name")],
            "Tamish",
            "First Name",
        )
        assert result is True
        assert await page.input_value("#first_name") == "Tamish"

        await browser.close()


# ── Registry completeness ─────────────────────────────────────────────────────

def test_all_four_fillers_registered():
    """All four ATS fillers should be in the registry."""
    platform_names = {cls.platform_name for cls in _FILLER_CLASSES}
    assert "Greenhouse" in platform_names
    assert "Lever" in platform_names
    assert "Workday" in platform_names
    assert "SmartRecruiters" in platform_names
    assert len(_FILLER_CLASSES) == 4


def test_smartrecruiters_selectors_structure():
    """SmartRecruiters selectors should have at least 2 fallbacks per field."""
    required_fields = ["first_name", "last_name", "email", "phone", "linkedin", "resume"]
    for field in required_fields:
        assert field in SmartRecruitersFiller.SELECTORS, f"Missing selector: {field}"
        assert len(SmartRecruitersFiller.SELECTORS[field]) >= 2, (
            f"Field '{field}' needs at least 2 fallback selectors"
        )


# ── URL validation in fillers ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_url_field_rejects_invalid(candidate):
    """validate_url_field should reject malformed URLs and return None."""
    html = "<html><body><input type='text' id='url' /></body></html>"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = SmartRecruitersFiller(page, candidate)

        # Invalid URL should return None (meaning skip)
        result = filler.validate_url_field("not-a-real-url", "LinkedIn URL")
        assert result is None
        assert "LinkedIn URL" in filler._skipped_fields

        # Valid URL should pass through
        result = filler.validate_url_field("https://linkedin.com/in/test", "LinkedIn URL 2")
        assert result == "https://linkedin.com/in/test"

        await browser.close()
