"""Greenhouse ATS form filler.

Targets job application forms on boards.greenhouse.io.
Uses a primary + fallback locator strategy for each field.
"""

from __future__ import annotations

import logging

from playwright.async_api import Page

from src.fillers.base import ATSFormFiller
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


class GreenhouseFiller(ATSFormFiller):
    """Form filler for Greenhouse ATS (boards.greenhouse.io)."""

    platform_name = "Greenhouse"

    # Greenhouse-specific selectors: primary and fallback for each field
    SELECTORS = {
        "first_name": [
            "#first_name",
            'input[name="job_application[first_name]"]',
            'input[autocomplete="given-name"]',
        ],
        "last_name": [
            "#last_name",
            'input[name="job_application[last_name]"]',
            'input[autocomplete="family-name"]',
        ],
        "email": [
            "#email",
            'input[name="job_application[email]"]',
            'input[type="email"]',
        ],
        "phone": [
            "#phone",
            'input[name="job_application[phone]"]',
            'input[type="tel"]',
        ],
        "resume": [
            'input[type="file"][id*="resume"]',
            'input[type="file"]',
            'label:has-text("Resume") >> input[type="file"]',
        ],
        "linkedin": [
            'input[name*="linkedin"]',
            'input[id*="linkedin"]',
            'label:has-text("LinkedIn") + input',
            'label:has-text("LinkedIn") >> input',
        ],
        "location": [
            'input[name*="location"]',
            'input[id*="location"]',
            'label:has-text("Location") + input',
            'label:has-text("Location") >> input',
        ],
        "website": [
            'input[name*="website"]',
            'input[id*="portfolio"]',
            'label:has-text("Website") + input',
            'label:has-text("Website") >> input',
        ],
    }

    async def detect(self) -> bool:
        """Return True if the current page is a Greenhouse application form."""
        url = self.page.url.lower()
        return "greenhouse.io" in url or "greenhouse" in url

    async def fill(self) -> FillResult:
        """Fill all known fields on a Greenhouse application form.
        
        Fills fields in order: personal info → resume → links.
        Halts for human review after completion.
        
        Returns:
            FillResult with details of what was filled/failed/skipped.
        """
        self.logger.info("")
        self.logger.info("🌿 Starting Greenhouse form fill...")
        self.logger.info("   URL: %s", self.page.url)
        self.logger.info("")

        personal = self.candidate.personal

        # --- Personal Information ---
        self.logger.info("--- Filling Personal Information ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["first_name"]],
            personal.first_name,
            "First Name",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["last_name"]],
            personal.last_name,
            "Last Name",
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
            # Try each resume file input selector
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
            [self.page.locator(s) for s in self.SELECTORS["website"]],
            personal.website,
            "Website/Portfolio",
        )

        # --- Location ---
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["location"]],
            personal.location,
            "Location",
        )

        # ⛔ HALT — Never submit
        return self.halt_for_review()
