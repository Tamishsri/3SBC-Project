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
        "how_did_you_hear": [
            '[data-automation-id="sourceOfHire"]',
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

        # --- Address (if available) ---
        if personal.location:
            self.logger.info("--- Filling Address ---")
            # Try filling city from location
            parts = personal.location.split(",")
            city = parts[0].strip() if parts else personal.location

            await self.safe_fill_with_fallbacks(
                [self.page.locator(s) for s in self.SELECTORS["city"]],
                city,
                "City",
                timeout_ms=3000,
            )

        # --- Links ---
        self.logger.info("--- Filling Links ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["linkedin"]],
            personal.linkedin_url,
            "LinkedIn URL",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["website"]],
            personal.website,
            "Website/Portfolio",
        )

        # HALT — Never submit
        return self.halt_for_review()
