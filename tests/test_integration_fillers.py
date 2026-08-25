"""Integration tests running Playwright fillers against local HTML test forms."""

import pytest
from playwright.async_api import async_playwright
import tempfile
import os

from src.models import CandidateData, PersonalInfo, WorkExperience, Education
from src.fillers.greenhouse import GreenhouseFiller
from src.fillers.lever import LeverFiller


@pytest.fixture
def candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+91-9876543210",
            linkedin_url="https://linkedin.com/in/tamishsri",
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
        skills=["Python", "Playwright"],
    )


@pytest.mark.asyncio
async def test_greenhouse_filler_execution_flow(candidate):
    """Test GreenhouseFiller fills fields correctly on a Greenhouse-like HTML DOM without error."""
    greenhouse_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Greenhouse Job Application</title></head>
    <body>
        <form id="application_form">
            <input type="text" id="first_name" name="job_application[first_name]" />
            <input type="text" id="last_name" name="job_application[last_name]" />
            <input type="email" id="email" name="job_application[email]" />
            <input type="tel" id="phone" name="job_application[phone]" />
            <input type="text" name="job_application[location]" id="location" />
            <input type="text" name="job_application[answers_attributes][0][text_value]" id="job_application_answers_attributes_0_text_value" placeholder="LinkedIn Profile" />
            <label>Website</label><input type="text" name="job_application[website]" id="website" />
        </form>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(greenhouse_html)

        filler = GreenhouseFiller(page, candidate)
        # Force detect to True for test page
        result = await filler.fill()

        assert result.ats_platform == "Greenhouse"
        assert "First Name" in result.filled_fields
        assert "Last Name" in result.filled_fields
        assert "Email" in result.filled_fields
        assert "Phone" in result.filled_fields
        assert "Location" in result.filled_fields

        # Verify values in DOM
        assert await page.input_value("#first_name") == "Tamish"
        assert await page.input_value("#last_name") == "Sridatta"
        assert await page.input_value("#email") == "tamish@example.com"
        assert await page.input_value("#phone") == "+91-9876543210"

        await browser.close()


@pytest.mark.asyncio
async def test_lever_filler_execution_flow(candidate):
    """Test LeverFiller fills fields correctly on a Lever-like HTML DOM without error."""
    lever_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Lever Job Application</title></head>
    <body>
        <form id="application-form">
            <input type="text" name="name" placeholder="Full name" />
            <input type="email" name="email" placeholder="Email" />
            <input type="tel" name="phone" placeholder="Phone" />
            <input type="text" name="org" placeholder="Current company" />
            <input type="text" name="urls[LinkedIn]" placeholder="LinkedIn URL" />
            <input type="text" name="urls[Portfolio]" placeholder="Portfolio URL" />
        </form>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(lever_html)

        filler = LeverFiller(page, candidate)
        result = await filler.fill()

        assert result.ats_platform == "Lever"
        assert "Full Name" in result.filled_fields
        assert "Email" in result.filled_fields
        assert "Phone" in result.filled_fields
        assert "Current Company" in result.filled_fields
        assert "LinkedIn URL" in result.filled_fields

        # Verify values in DOM
        assert await page.input_value('input[name="name"]') == "Tamish Sridatta"
        assert await page.input_value('input[name="email"]') == "tamish@example.com"
        assert await page.input_value('input[name="org"]') == "3SBC Tech"

        await browser.close()
