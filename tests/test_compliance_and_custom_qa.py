"""Unit and DOM integration tests for Work Auth, EEOC Demographics, and Custom Q&A matching."""

import pytest
from playwright.async_api import async_playwright

from src.models import CandidateData, PersonalInfo, WorkAuthorization, Demographics
from src.fillers.base import ATSFormFiller
from src.fillers.greenhouse import GreenhouseFiller


class DummyFiller(ATSFormFiller):
    platform_name = "Dummy ATS"

    async def detect(self) -> bool:
        return True

    async def fill(self):
        await self.fill_compliance_and_work_auth()
        await self.fill_custom_questions()
        return self.halt_for_review()


@pytest.fixture
def enriched_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        ),
        work_authorization=WorkAuthorization(
            authorized_to_work=True,
            requires_sponsorship=False,
            notice_period_days=30,
            expected_salary="$140,000",
        ),
        demographics=Demographics(
            gender="Male",
            race_ethnicity="Asian",
            veteran_status="I am not a protected veteran",
            disability_status="No, I don't have a disability",
        ),
        custom_answers={
            "willing to travel": "Yes, up to 25%",
            "preferred IDE": "VS Code",
        },
    )


@pytest.mark.asyncio
async def test_compliance_select_dropdowns(enriched_candidate):
    """Test standard select-based EEOC and work authorization questions."""
    html = """
    <html>
    <body>
        <label>Are you legally authorized to work in the United States?
            <select id="work_auth">
                <option value="">-- Select --</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
            </select>
        </label>
        <label>Will you require visa sponsorship now or in the future?
            <select id="visa_spon">
                <option value="">-- Select --</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
            </select>
        </label>
        <label>Gender
            <select id="gender_select">
                <option value="">-- Select --</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Decline to self-identify">Decline to self-identify</option>
            </select>
        </label>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = DummyFiller(page, enriched_candidate)
        await filler.fill_compliance_and_work_auth()

        # Check values
        assert await page.locator("#work_auth").input_value() == "Yes"
        assert await page.locator("#visa_spon").input_value() == "No"
        assert await page.locator("#gender_select").input_value() == "Male"

        await browser.close()


@pytest.mark.asyncio
async def test_compliance_radio_buttons(enriched_candidate):
    """Test radio button-based compliance questions."""
    html = """
    <html>
    <body>
        <fieldset>
            <legend>Are you legally authorized to work?</legend>
            <label><input type="radio" name="auth" value="Yes" /> Yes</label>
            <label><input type="radio" name="auth" value="No" /> No</label>
        </fieldset>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = DummyFiller(page, enriched_candidate)
        await filler.fill_compliance_and_work_auth()

        radio_yes = page.locator('input[value="Yes"]')
        assert await radio_yes.is_checked() is True

        await browser.close()


@pytest.mark.asyncio
async def test_custom_questions_matcher(enriched_candidate):
    """Test dynamic matching of custom questions (notice period, expected salary, custom dict)."""
    html = """
    <html>
    <body>
        <label>What is your Notice Period (in days)?
            <input type="text" id="notice_input" />
        </label>
        <label>Expected Salary / Compensation
            <input type="text" id="salary_input" />
        </label>
        <label>Are you willing to travel for business?
            <input type="text" id="travel_input" />
        </label>
    </body>
    </html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        filler = DummyFiller(page, enriched_candidate)
        await filler.fill_custom_questions()

        assert await page.locator("#notice_input").input_value() == "30"
        assert await page.locator("#salary_input").input_value() == "$140,000"
        assert await page.locator("#travel_input").input_value() == "Yes, up to 25%"

        await browser.close()
