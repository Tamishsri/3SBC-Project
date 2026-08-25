"""Lever ATS form filler.

Targets job application forms on jobs.lever.co.
"""

from __future__ import annotations

import logging

from playwright.async_api import Page

from src.fillers.base import ATSFormFiller
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


class LeverFiller(ATSFormFiller):
    """Form filler for Lever ATS (jobs.lever.co)."""

    platform_name = "Lever"

    # Lever-specific selectors
    SELECTORS = {
        "full_name": [
            'input[name="name"]',
            'input[placeholder*="Full name"]',
            'input[placeholder*="full name"]',
        ],
        "email": [
            'input[name="email"]',
            'input[type="email"]',
            'input[placeholder*="Email"]',
        ],
        "phone": [
            'input[name="phone"]',
            'input[type="tel"]',
            'input[placeholder*="Phone"]',
        ],
        "resume": [
            'input[name="resume"]',
            'input[type="file"]',
        ],
        "linkedin": [
            'input[name="urls[LinkedIn]"]',
            'input[name*="LinkedIn"]',
            'input[placeholder*="LinkedIn"]',
        ],
        "current_company": [
            'input[name="org"]',
            'input[placeholder*="Current company"]',
            'input[placeholder*="company"]',
        ],
        "github": [
            'input[name="urls[GitHub]"]',
            'input[name*="GitHub"]',
            'input[placeholder*="GitHub"]',
        ],
        "portfolio": [
            'input[name="urls[Portfolio]"]',
            'input[name*="Portfolio"]',
            'input[placeholder*="Portfolio"]',
        ],
    }

    async def detect(self) -> bool:
        """Return True if the current page is a Lever application form."""
        url = self.page.url.lower()
        return "lever.co" in url

    async def fill(self) -> FillResult:
        """Fill all known fields on a Lever application form.
        
        Note: Lever uses a single 'Full Name' field rather than separate
        first/last name fields.
        
        Returns:
            FillResult with details of what was filled/failed/skipped.
        """
        self.logger.info("")
        self.logger.info("🎯 Starting Lever form fill...")
        self.logger.info("   URL: %s", self.page.url)
        self.logger.info("")

        personal = self.candidate.personal

        # --- Personal Information ---
        self.logger.info("--- Filling Personal Information ---")

        # Lever uses a combined full name field
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["full_name"]],
            personal.full_name,
            "Full Name",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["email"]],
            personal.email,
            "Email",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["phone"]],
            personal.phone,
            "Phone",
        )

        # --- Resume Upload ---
        self.logger.info("--- Uploading Resume ---")

        if self.candidate.resume_file_path:
            for selector in self.SELECTORS["resume"]:
                uploaded = await self.safe_upload_file(
                    self.page.locator(selector),
                    self.candidate.resume_file_path,
                    "Resume",
                )
                if uploaded:
                    break
        else:
            self.logger.info("⏭  Skipping Resume upload — no file path provided")
            self._skipped_fields.append("Resume")

        # --- Links ---
        self.logger.info("--- Filling Links ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["linkedin"]],
            personal.linkedin_url,
            "LinkedIn URL",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["portfolio"]],
            personal.website,
            "Portfolio/Website",
        )

        # --- Current Company (from most recent experience) ---
        current_company = None
        if self.candidate.experience:
            current_company = self.candidate.experience[0].company

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["current_company"]],
            current_company,
            "Current Company",
        )

        # ⛔ HALT — Never submit
        return self.halt_for_review()
