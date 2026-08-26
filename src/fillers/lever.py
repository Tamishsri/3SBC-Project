"""Lever ATS form filler.

Targets job application forms on jobs.lever.co.
Handles cover letter, GitHub, location, additional notes, and more fields.
"""

from __future__ import annotations

import logging

from src.fillers.base import ATSFormFiller
from src.models import FillResult

logger = logging.getLogger(__name__)


class LeverFiller(ATSFormFiller):
    """Form filler for Lever ATS (jobs.lever.co).

    Supports:
    - Full name (Lever uses a single combined field)
    - Email, Phone
    - Resume upload
    - LinkedIn, GitHub, Portfolio, Twitter
    - Current company (from most recent experience)
    - Cover letter textarea
    - Additional information/notes field
    """

    platform_name = "Lever"

    # Lever-specific selectors
    SELECTORS = {
        "full_name": [
            'input[name="name"]',
            'input[placeholder*="Full name" i]',
            'input[placeholder*="Your name" i]',
            'label:has-text("Full name") >> input',
        ],
        "email": [
            'input[name="email"]',
            'input[type="email"]',
            'input[placeholder*="Email" i]',
        ],
        "phone": [
            'input[name="phone"]',
            'input[type="tel"]',
            'input[placeholder*="Phone" i]',
        ],
        "resume": [
            'input[name="resume"]',
            'input[type="file"]',
        ],
        "linkedin": [
            'input[name="urls[LinkedIn]"]',
            'input[name*="LinkedIn" i]',
            'input[placeholder*="LinkedIn" i]',
        ],
        "github": [
            'input[name="urls[GitHub]"]',
            'input[name*="GitHub" i]',
            'input[placeholder*="GitHub" i]',
        ],
        "twitter": [
            'input[name="urls[Twitter]"]',
            'input[placeholder*="Twitter" i]',
        ],
        "portfolio": [
            'input[name="urls[Portfolio]"]',
            'input[name*="Portfolio" i]',
            'input[placeholder*="Portfolio" i]',
            'input[placeholder*="Website" i]',
        ],
        "current_company": [
            'input[name="org"]',
            'input[placeholder*="Current company" i]',
            'input[placeholder*="Company" i]',
        ],
        "cover_letter": [
            'textarea[name="comments"]',
            'textarea[placeholder*="cover letter" i]',
            'textarea[placeholder*="Tell us" i]',
            'textarea[placeholder*="Add a note" i]',
            'label:has-text("Additional information") >> textarea',
            'label:has-text("Cover letter") >> textarea',
        ],
        "additional_info": [
            'textarea[name="comments"]',
            'textarea[name="additionalInfo"]',
            'label:has-text("Additional") >> textarea',
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
        self.logger.info("Starting Lever form fill...")
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

        # --- Current Company (from most recent experience) ---
        current_company = None
        if self.candidate.experience:
            current = next(
                (exp for exp in self.candidate.experience if exp.is_current),
                self.candidate.experience[0],
            )
            current_company = current.company

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["current_company"]],
            current_company,
            "Current Company",
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
            self.logger.info("Skipping Resume upload - no file path provided")
            self._skipped_fields.append("Resume")

        # --- Links ---
        self.logger.info("--- Filling Links ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["linkedin"]],
            self.validate_url_field(personal.linkedin_url, "LinkedIn URL"),
            "LinkedIn URL",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["github"]],
            self.validate_url_field(personal.github_url, "GitHub URL"),
            "GitHub URL",
        )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["portfolio"]],
            self.validate_url_field(personal.website, "Portfolio/Website"),
            "Portfolio/Website",
        )

        # --- Cover Letter ---
        self.logger.info("--- Filling Cover Letter ---")

        cover_letter_text = self.candidate.cover_letter
        if not cover_letter_text and self.candidate.experience:
            recent = self.candidate.experience[0]
            cover_letter_text = (
                f"I am excited to apply for this position. In my most recent role as "
                f"{recent.title} at {recent.company}, I developed strong expertise relevant "
                f"to this opportunity. My skills in {', '.join(self.candidate.skills[:5])} "
                f"align well with what you are looking for."
            )

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["cover_letter"]],
            cover_letter_text,
            "Cover Letter / Additional Info",
        )

        # --- Work Authorization, EEOC Compliance & Custom Questions ---
        await self.fill_compliance_and_work_auth()
        await self.fill_custom_questions()

        # Multi-page wizard advance
        advanced = await self.advance_to_next_wizard_page()
        if not advanced:
            await self.detect_next_page()

        # HALT — Never submit
        return self.halt_for_review()
