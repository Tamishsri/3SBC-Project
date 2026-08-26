"""Greenhouse ATS form filler.

Targets job application forms on boards.greenhouse.io.
Handles both direct-hosted forms AND iframes embedded on company career sites.
Uses a primary + fallback locator strategy for each field.
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import FrameLocator, Page, TimeoutError as PlaywrightTimeoutError

from src.fillers.base import ATSFormFiller
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


class GreenhouseFiller(ATSFormFiller):
    """Form filler for Greenhouse ATS (boards.greenhouse.io).

    Supports:
    - Direct application pages (boards.greenhouse.io/*)
    - Embedded iframes on company career pages
    - Cover letter text field
    - LinkedIn, Website, Location, GitHub
    - EEOC/demographic fields (selects — skipped if dropdowns aren't found)
    """

    platform_name = "Greenhouse"

    # Greenhouse-specific selectors: primary and fallback for each field
    SELECTORS = {
        "first_name": [
            "#first_name",
            'input[name="job_application[first_name]"]',
            'input[name="first_name"]',
            'input[autocomplete="given-name"]',
            'label:has-text("First Name") >> input',
        ],
        "last_name": [
            "#last_name",
            'input[name="job_application[last_name]"]',
            'input[name="last_name"]',
            'input[autocomplete="family-name"]',
            'label:has-text("Last Name") >> input',
        ],
        "email": [
            "#email",
            'input[name="job_application[email]"]',
            'input[name="email"]',
            'input[type="email"]',
        ],
        "phone": [
            "#phone",
            'input[name="job_application[phone]"]',
            'input[name="phone"]',
            'input[type="tel"]',
        ],
        "resume": [
            'input#resume[type="file"]',
            'input[type="file"][id*="resume"]',
            'input[name="resume"]',
            'input[type="file"]',
        ],
        "cover_letter_text": [
            'textarea#cover_letter_text',
            'textarea[name="cover_letter_text"]',
            'textarea[name="job_application[cover_letter_text]"]',
            'label:has-text("Cover Letter") >> textarea',
        ],
        "linkedin": [
            'input[name*="linkedin" i]',
            'input[id*="linkedin" i]',
            'label:has-text("LinkedIn") ~ input',
            'label:has-text("LinkedIn") >> input',
        ],
        "github": [
            'input[name*="github" i]',
            'input[id*="github" i]',
            'label:has-text("GitHub") ~ input',
            'label:has-text("GitHub") >> input',
        ],
        "website": [
            'input[name*="website" i]',
            'input[id*="portfolio" i]',
            'input[id*="website" i]',
            'label:has-text("Website") ~ input',
            'label:has-text("Portfolio") ~ input',
            'label:has-text("Website") >> input',
        ],
        "location": [
            'input[name*="location" i]',
            'input[id*="location" i]',
            'label:has-text("Location") ~ input',
            'label:has-text("Location") >> input',
        ],
    }

    # Iframe selectors for embedded Greenhouse forms
    IFRAME_SELECTORS = [
        "iframe#grnhse_iframe",
        'iframe[src*="greenhouse.io"]',
        'iframe[title*="Application"]',
    ]

    async def _get_form_context(self):
        """Return the context to use for locators — either page or iframe.

        Greenhouse forms are sometimes embedded in iframes on company career pages.
        This detects that case and returns the correct frame context.

        Returns:
            Page or FrameLocator depending on whether the form is in an iframe.
        """
        for iframe_selector in self.IFRAME_SELECTORS:
            try:
                iframe = self.page.locator(iframe_selector)
                count = await iframe.count()
                if count > 0:
                    self.logger.info(
                        "Greenhouse form detected inside iframe (%s)",
                        iframe_selector,
                    )
                    return self.page.frame_locator(iframe_selector)
            except Exception:
                continue

        # No iframe — use page directly
        return self.page

    async def detect(self) -> bool:
        """Return True if the current page is a Greenhouse application form."""
        url = self.page.url.lower()
        if "greenhouse.io" in url:
            return True

        # Check for embedded iframe even if not on greenhouse.io domain
        for sel in self.IFRAME_SELECTORS:
            try:
                count = await self.page.locator(sel).count()
                if count > 0:
                    return True
            except Exception:
                continue

        return False

    async def fill(self) -> FillResult:
        """Fill all known fields on a Greenhouse application form.

        Handles both direct pages and embedded iframes.
        Fills in order: personal info → resume → cover letter → links → location.
        Halts for human review after completion.

        Returns:
            FillResult with details of what was filled/failed/skipped.
        """
        self.logger.info("")
        self.logger.info("Starting Greenhouse form fill...")
        self.logger.info("   URL: %s", self.page.url)
        self.logger.info("")

        # Detect iframe vs direct page
        ctx = await self._get_form_context()
        personal = self.candidate.personal

        # --- Personal Information ---
        self.logger.info("--- Filling Personal Information ---")

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["first_name"]],
            personal.first_name,
            "First Name",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["last_name"]],
            personal.last_name,
            "Last Name",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["email"]],
            personal.email,
            "Email",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["phone"]],
            personal.phone,
            "Phone",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["location"]],
            personal.location,
            "Location",
        )

        # --- Resume Upload ---
        self.logger.info("--- Uploading Resume ---")

        if self.candidate.resume_file_path:
            for selector in self.SELECTORS["resume"]:
                uploaded = await self.safe_upload_file(
                    ctx.locator(selector),
                    self.candidate.resume_file_path,
                    "Resume",
                )
                if uploaded:
                    break
        else:
            self.logger.info("Skipping Resume upload - no file path provided")
            self._skipped_fields.append("Resume")

        # --- Cover Letter ---
        self.logger.info("--- Filling Cover Letter ---")

        # Build a cover letter from experience if no explicit cover letter text
        cover_letter_text = getattr(self.candidate, "cover_letter", None)
        if not cover_letter_text and self.candidate.experience:
            recent = self.candidate.experience[0]
            cover_letter_text = (
                f"I am excited to apply for this position. In my most recent role as "
                f"{recent.title} at {recent.company}, I developed strong expertise relevant "
                f"to this opportunity. My skills in {', '.join(self.candidate.skills[:5])} "
                f"align well with what you are looking for."
            )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["cover_letter_text"]],
            cover_letter_text,
            "Cover Letter",
        )

        # --- Links ---
        self.logger.info("--- Filling Links ---")

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["linkedin"]],
            self.validate_url_field(personal.linkedin_url, "LinkedIn URL"),
            "LinkedIn URL",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["github"]],
            self.validate_url_field(personal.github_url, "GitHub URL"),
            "GitHub URL",
        )

        await self.safe_fill_with_fallbacks(
            [ctx.locator(s) for s in self.SELECTORS["website"]],
            self.validate_url_field(personal.website, "Website/Portfolio"),
            "Website/Portfolio",
        )

        # Check for multi-page form
        await self.detect_next_page()

        # HALT — Never submit
        return self.halt_for_review()
