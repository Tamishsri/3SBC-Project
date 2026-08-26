"""Workday ATS form filler.

Targets job application forms on workday.com (wd1/wd2/wd3/wd5.myworkdayjobs.com).
Workday has a heavy SPA/React architecture with dynamic selectors.
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Error as PlaywrightError

from src.fillers.base import ATSFormFiller
from src.models import FillResult

logger = logging.getLogger(__name__)


class WorkdayFiller(ATSFormFiller):
    """Form filler for Workday ATS (*.myworkdayjobs.com and workday.com).
    
    Workday uses a heavy React SPA. Fields are rendered dynamically and
    require explicit waits for each section to load before interacting.
    """

    platform_name = "Workday"

    # Workday uses data-automation-id attributes heavily — most reliable
    SELECTORS = {
        "first_name": [
            '[data-automation-id="legalNameSection_firstName"]',
            '[data-automation-id="firstName"]',
            'input[placeholder*="First Name"]',
        ],
        "last_name": [
            '[data-automation-id="legalNameSection_lastName"]',
            '[data-automation-id="lastName"]',
            'input[placeholder*="Last Name"]',
        ],
        "email": [
            '[data-automation-id="email"]',
            'input[type="email"]',
            'input[placeholder*="Email"]',
        ],
        "phone": [
            '[data-automation-id="phone-number"]',
            '[data-automation-id="phoneNumber"]',
            'input[placeholder*="Phone"]',
        ],
        "address_line1": [
            '[data-automation-id="addressSection_addressLine1"]',
            'input[placeholder*="Address"]',
        ],
        "city": [
            '[data-automation-id="addressSection_city"]',
            'input[placeholder*="City"]',
        ],
        "state": [
            '[data-automation-id="addressSection_countryRegion"]',
        ],
        "postal_code": [
            '[data-automation-id="addressSection_postalCode"]',
            'input[placeholder*="Zip"]',
            'input[placeholder*="Postal"]',
        ],
        "linkedin": [
            'input[placeholder*="LinkedIn"]',
            'label:has-text("LinkedIn") >> input',
        ],
        "website": [
            'input[placeholder*="Website"]',
            'input[placeholder*="Portfolio"]',
            'label:has-text("Website") >> input',
        ],
        "resume": [
            'input[data-automation-id="file-upload-input"]',
            '[data-automation-id="file-upload-drop-zone"] input[type="file"]',
            'input[type="file"][accept*="pdf"]',
            'input[type="file"]',
        ],
    }

    async def detect(self) -> bool:
        """Return True if the current page is a Workday application form."""
        url = self.page.url.lower()
        return any(
            pattern in url
            for pattern in [
                "myworkdayjobs.com",
                "workday.com",
                "wd1.myworkday",
                "wd2.myworkday",
                "wd3.myworkday",
                "wd5.myworkday",
            ]
        )

    async def _wait_for_workday_load(self) -> None:
        """Wait for Workday's SPA to finish loading before interacting."""
        try:
            # Wait for Workday's React root to be ready
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            self.logger.warning("Workday page load timeout — proceeding anyway")

    async def fill(self) -> FillResult:
        """Fill all known fields on a Workday application form.

        Workday forms load dynamically — we wait for the SPA to settle
        before attempting each section.

        Returns:
            FillResult with details of what was filled/failed/skipped.
        """
        from src.normalizer import parse_location

        self.logger.info("")
        self.logger.info("Starting Workday form fill...")
        self.logger.info("   URL: %s", self.page.url)
        self.logger.info("   NOTE: Workday is a React SPA — using extended timeouts")
        self.logger.info("")

        # Wait for Workday to load
        await self._wait_for_workday_load()

        personal = self.candidate.personal

        # --- Personal Information ---
        self.logger.info("--- Filling Personal Information ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["first_name"]],
            personal.first_name,
            "First Name",
            timeout_ms=5000,
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["last_name"]],
            personal.last_name,
            "Last Name",
            timeout_ms=5000,
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["email"]],
            personal.email,
            "Email",
            timeout_ms=5000,
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["phone"]],
            personal.phone,
            "Phone",
            timeout_ms=5000,
        )

        # --- Resume Upload ---
        self.logger.info("--- Uploading Resume ---")
        if self.candidate.resume_file_path:
            for selector in self.SELECTORS.get("resume", []):
                uploaded = await self.safe_upload_file(
                    self.page.locator(selector),
                    self.candidate.resume_file_path,
                    "Resume",
                )
                if uploaded:
                    break
        else:
            self.logger.info("[SKIP] Resume upload - no file path provided")
            self._skipped_fields.append("Resume")

        # --- Address (if available) ---
        if personal.location:
            self.logger.info("--- Filling Address ---")
            parsed_loc = parse_location(personal.location)

            if parsed_loc.city:
                await self.safe_fill_with_fallbacks(
                    [self.page.locator(s) for s in self.SELECTORS["city"]],
                    parsed_loc.city,
                    "City",
                    timeout_ms=3000,
                )
            if parsed_loc.state_province:
                await self.safe_fill_with_fallbacks(
                    [self.page.locator(s) for s in self.SELECTORS["state"]],
                    parsed_loc.state_province,
                    "State/Province",
                    timeout_ms=3000,
                )

        # --- Links ---
        self.logger.info("--- Filling Links ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["linkedin"]],
            self.validate_url_field(personal.linkedin_url, "LinkedIn URL"),
            "LinkedIn URL",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["website"]],
            self.validate_url_field(personal.website, "Website/Portfolio"),
            "Website/Portfolio",
        )

        # --- Work Authorization, EEOC Compliance & Custom Questions ---
        await self.fill_compliance_and_work_auth()
        await self.fill_custom_questions()

        # Multi-page wizard advance (Workday has multiple step wizards)
        advanced = await self.advance_to_next_wizard_page()
        if advanced:
            # If advanced to next page, check for additional questions/EEOC on page 2/3
            self.logger.info("[WIZARD] Checking additional step fields on next page...")
            await self.fill_compliance_and_work_auth()
            await self.fill_custom_questions()
            await self.advance_to_next_wizard_page()
        else:
            await self.detect_next_page()

        # HALT — Never submit
        return self.halt_for_review()
