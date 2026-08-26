"""SmartRecruiters ATS form filler.

Targets job application forms on careers.smartrecruiters.com.
SmartRecruiters is used by thousands of companies worldwide.
"""

from __future__ import annotations

import logging

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.fillers.base import ATSFormFiller
from src.models import FillResult

logger = logging.getLogger(__name__)


class SmartRecruitersFiller(ATSFormFiller):
    """Form filler for SmartRecruiters ATS (careers.smartrecruiters.com).

    SmartRecruiters uses a React SPA with data-test-id attributes.
    Supports personal info, resume upload, cover letter, and links.
    """

    platform_name = "SmartRecruiters"

    SELECTORS = {
        "first_name": [
            '[data-test-id="first-name"]',
            'input[name="firstName"]',
            'input[placeholder*="First name" i]',
            'label:has-text("First name") >> input',
        ],
        "last_name": [
            '[data-test-id="last-name"]',
            'input[name="lastName"]',
            'input[placeholder*="Last name" i]',
            'label:has-text("Last name") >> input',
        ],
        "email": [
            '[data-test-id="email"]',
            'input[name="email"]',
            'input[type="email"]',
        ],
        "phone": [
            '[data-test-id="phone"]',
            'input[name="phone"]',
            'input[type="tel"]',
        ],
        "location": [
            '[data-test-id="location"]',
            'input[name="location"]',
            'input[placeholder*="Location" i]',
        ],
        "linkedin": [
            '[data-test-id="linkedin"]',
            'input[name="linkedIn"]',
            'input[placeholder*="LinkedIn" i]',
            'label:has-text("LinkedIn") >> input',
        ],
        "website": [
            '[data-test-id="website"]',
            'input[name="website"]',
            'input[placeholder*="Website" i]',
            'input[placeholder*="Portfolio" i]',
        ],
        "resume": [
            'input[data-test-id="resume-upload"]',
            'input[type="file"][accept*="pdf"]',
            'input[type="file"]',
        ],
        "cover_letter": [
            'textarea[data-test-id="cover-letter"]',
            'textarea[name="coverLetter"]',
            'textarea[placeholder*="cover letter" i]',
            'label:has-text("Cover letter") >> textarea',
        ],
    }

    # SmartRecruiters "Next page" button selectors
    NEXT_PAGE_SELECTORS = [
        '[data-test-id="btn-next"]',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]

    async def detect(self) -> bool:
        """Return True if the current page is a SmartRecruiters form."""
        url = self.page.url.lower()
        return any(pattern in url for pattern in [
            "smartrecruiters.com",
            "careers.smartrecruiters",
        ])

    async def _check_for_next_page(self) -> bool:
        """Check if a 'Next' button is present and warn the user."""
        for selector in self.NEXT_PAGE_SELECTORS:
            try:
                count = await self.page.locator(selector).count()
                if count > 0:
                    self.logger.warning(
                        "[!!] MULTI-PAGE FORM DETECTED: A 'Next' or 'Continue' "
                        "button was found. This filler only fills the FIRST page. "
                        "Please click 'Next' manually and re-run for subsequent pages."
                    )
                    return True
            except Exception:
                continue
        return False

    async def fill(self) -> FillResult:
        """Fill all known fields on a SmartRecruiters application form.

        Returns:
            FillResult with details of what was filled/failed/skipped.
        """
        self.logger.info("")
        self.logger.info("Starting SmartRecruiters form fill...")
        self.logger.info("   URL: %s", self.page.url)
        self.logger.info("")

        personal = self.candidate.personal

        # --- Personal Information ---
        self.logger.info("--- Filling Personal Information ---")

        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["first_name"]],
            personal.first_name, "First Name",
        )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["last_name"]],
            personal.last_name, "Last Name",
        )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["email"]],
            personal.email, "Email",
        )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["phone"]],
            personal.phone, "Phone",
        )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["location"]],
            personal.location, "Location",
        )

        # --- Resume Upload ---
        self.logger.info("--- Uploading Resume ---")
        if self.candidate.resume_file_path:
            for selector in self.SELECTORS["resume"]:
                uploaded = await self.safe_upload_file(
                    self.page.locator(selector),
                    self.candidate.resume_file_path, "Resume",
                )
                if uploaded:
                    break
        else:
            self.logger.info("[SKIP] Resume upload - no file path provided")
            self._skipped_fields.append("Resume")

        # --- Links ---
        self.logger.info("--- Filling Links ---")
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["linkedin"]],
            personal.linkedin_url, "LinkedIn URL",
        )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["website"]],
            personal.website, "Website/Portfolio",
        )

        # --- Cover Letter ---
        self.logger.info("--- Filling Cover Letter ---")
        cover_letter_text = self.candidate.cover_letter
        if not cover_letter_text and self.candidate.experience:
            recent = self.candidate.experience[0]
            cover_letter_text = (
                f"I am excited to apply for this position. In my most recent role as "
                f"{recent.title} at {recent.company}, I developed strong expertise "
                f"relevant to this opportunity. My skills in "
                f"{', '.join(self.candidate.skills[:5])} align well with your requirements."
            )
        await self.safe_fill_with_fallbacks(
            [self.page.locator(s) for s in self.SELECTORS["cover_letter"]],
            cover_letter_text, "Cover Letter",
        )

        # --- Work Authorization, EEOC Compliance & Custom Questions ---
        await self.fill_compliance_and_work_auth()
        await self.fill_custom_questions()

        # Multi-page wizard advance
        advanced = await self.advance_to_next_wizard_page()
        if not advanced:
            await self._check_for_next_page()

        # HALT — Never submit
        return self.halt_for_review()
