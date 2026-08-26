"""Tests for the multi-page wizard advancer and submit button safety guards."""

import pytest
from playwright.async_api import async_playwright

from src.models import CandidateData, PersonalInfo
from src.fillers.base import ATSFormFiller


class WizardTestFiller(ATSFormFiller):
    platform_name = "Wizard ATS"

    async def detect(self) -> bool:
        return True

    async def fill(self):
        return self.halt_for_review()


@pytest.fixture
def base_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        )
    )


@pytest.mark.asyncio
async def test_wizard_advances_when_multi_page_enabled(base_candidate):
    """Verify that advance_to_next_wizard_page clicks 'Next' button."""
    html = """
    <html>
    <body>
        <div id="page1">Page 1 Content</div>
        <button id="next_btn" onclick="document.getElementById('page1').innerText = 'Page 2 Content'">Next</button>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = WizardTestFiller(page, base_candidate, multi_page=True)
        advanced = await filler.advance_to_next_wizard_page()

        assert advanced is True
        assert await page.locator("#page1").inner_text() == "Page 2 Content"

        await browser.close()


@pytest.mark.asyncio
async def test_wizard_safety_guard_never_clicks_submit(base_candidate):
    """Critical Iron Rule Test: advance_to_next_wizard_page must NEVER click a Submit or Apply button."""
    html = """
    <html>
    <body>
        <div id="status">Not Submitted</div>
        <button id="submit_btn" onclick="document.getElementById('status').innerText = 'SUBMITTED DANGER'">Submit Application</button>
        <button id="apply_btn" onclick="document.getElementById('status').innerText = 'APPLIED DANGER'">Apply Now</button>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = WizardTestFiller(page, base_candidate, multi_page=True)
        advanced = await filler.advance_to_next_wizard_page()

        # Should return False and NEVER click submit or apply
        assert advanced is False
        assert await page.locator("#status").inner_text() == "Not Submitted"

        await browser.close()


@pytest.mark.asyncio
async def test_wizard_disabled_by_default(base_candidate):
    """When multi_page=False (default), advance_to_next_wizard_page returns False without clicking."""
    html = """
    <html>
    <body>
        <button id="next_btn">Next</button>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = WizardTestFiller(page, base_candidate, multi_page=False)
        advanced = await filler.advance_to_next_wizard_page()
        assert advanced is False

        await browser.close()
