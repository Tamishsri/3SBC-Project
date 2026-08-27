"""Generic and Adaptive Web Form Filler for unlisted ATS platforms.

Employs semantic HTML5 heuristics (autocomplete, aria-label, placeholder,
name, id, label association) to fill standard job application forms on
platforms like Ashby, BambooHR, Jobvite, Taleo, Workable, Rippling, or
custom company career portals.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from playwright.async_api import Page

from src.exceptions import FieldNotFoundError
from src.fillers.base import ATSFormFiller
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


class GenericAdaptiveFiller(ATSFormFiller):
    """Adaptive heuristic form filler for arbitrary web job applications."""

    platform_name: ClassVar[str] = "Generic Web Form"

    # Semantic selector fallbacks for common fields
    FIRST_NAME_SELECTORS: ClassVar[list[str]] = [
        "input[autocomplete='given-name']",
        "input[name='firstName' i]",
        "input[name='first_name' i]",
        "input[name='fname' i]",
        "input[id*='first_name' i]",
        "input[id*='firstName' i]",
        "input[id*='fname' i]",
        "input[placeholder*='first name' i]",
        "input[aria-label*='first name' i]",
    ]

    LAST_NAME_SELECTORS: ClassVar[list[str]] = [
        "input[autocomplete='family-name']",
        "input[name='lastName' i]",
        "input[name='last_name' i]",
        "input[name='lname' i]",
        "input[id*='last_name' i]",
        "input[id*='lastName' i]",
        "input[id*='lname' i]",
        "input[placeholder*='last name' i]",
        "input[aria-label*='last name' i]",
    ]

    FULL_NAME_SELECTORS: ClassVar[list[str]] = [
        "input[autocomplete='name']",
        "input[name='name' i]",
        "input[name='fullName' i]",
        "input[name='full_name' i]",
        "input[id*='full_name' i]",
        "input[id*='fullName' i]",
        "input[placeholder*='full name' i]",
        "input[aria-label*='full name' i]",
    ]

    EMAIL_SELECTORS: ClassVar[list[str]] = [
        "input[type='email']",
        "input[autocomplete='email']",
        "input[name='email' i]",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[aria-label*='email' i]",
    ]

    PHONE_SELECTORS: ClassVar[list[str]] = [
        "input[type='tel']",
        "input[autocomplete='tel']",
        "input[name='phone' i]",
        "input[name*='phone' i]",
        "input[name*='mobile' i]",
        "input[id*='phone' i]",
        "input[id*='mobile' i]",
        "input[placeholder*='phone' i]",
        "input[aria-label*='phone' i]",
    ]

    LOCATION_SELECTORS: ClassVar[list[str]] = [
        "input[name*='location' i]",
        "input[name*='city' i]",
        "input[name*='address' i]",
        "input[id*='location' i]",
        "input[id*='city' i]",
        "input[placeholder*='location' i]",
        "input[placeholder*='city' i]",
        "input[aria-label*='location' i]",
    ]

    LINKEDIN_SELECTORS: ClassVar[list[str]] = [
        "input[name*='linkedin' i]",
        "input[id*='linkedin' i]",
        "input[placeholder*='linkedin' i]",
        "input[aria-label*='linkedin' i]",
    ]

    GITHUB_SELECTORS: ClassVar[list[str]] = [
        "input[name*='github' i]",
        "input[id*='github' i]",
        "input[placeholder*='github' i]",
        "input[aria-label*='github' i]",
    ]

    WEBSITE_SELECTORS: ClassVar[list[str]] = [
        "input[name*='portfolio' i]",
        "input[name*='website' i]",
        "input[name*='url' i]",
        "input[id*='portfolio' i]",
        "input[id*='website' i]",
        "input[placeholder*='portfolio' i]",
        "input[placeholder*='website' i]",
    ]

    RESUME_SELECTORS: ClassVar[list[str]] = [
        "input[type='file'][name*='resume' i]",
        "input[type='file'][name*='cv' i]",
        "input[type='file'][id*='resume' i]",
        "input[type='file'][id*='cv' i]",
        "input[type='file'][aria-label*='resume' i]",
        "input[type='file'][aria-label*='cv' i]",
        "input[type='file']",
    ]

    COVER_LETTER_SELECTORS: ClassVar[list[str]] = [
        "textarea[name*='cover' i]",
        "textarea[id*='cover' i]",
        "textarea[placeholder*='cover letter' i]",
        "textarea[aria-label*='cover letter' i]",
        "textarea[name*='letter' i]",
        "textarea[name*='message' i]",
        "textarea[name*='summary' i]",
        "textarea",
    ]

    async def detect(self) -> bool:
        """Detect whether the current page contains a plausible job application form."""
        try:
            # Check for at least an email input, name input, or file input
            has_email = await self.page.locator(
                "input[type='email'], input[name*='email' i], input[id*='email' i]"
            ).count() > 0
            has_name = await self.page.locator(
                "input[name*='name' i], input[id*='name' i], input[autocomplete*='name']"
            ).count() > 0
            has_file = await self.page.locator("input[type='file']").count() > 0
            has_form = await self.page.locator("form").count() > 0

            return (has_email or has_name or has_file) and (has_form or has_email)
        except Exception:
            return False

    async def fill(self) -> FillResult:
        """Fill recognized standard application fields using semantic heuristic matching."""
        self.logger.info("Executing Generic Adaptive Form Fill on: %s", self.page.url)

        p = self.candidate.personal

        # 1. Names: Try separate first/last name, then fall back to full name
        filled_first = False
        filled_last = False
        try:
            await self.safe_fill_with_fallbacks(self.FIRST_NAME_SELECTORS, p.first_name, field_name="First Name")
            filled_first = True
        except FieldNotFoundError:
            pass

        try:
            await self.safe_fill_with_fallbacks(self.LAST_NAME_SELECTORS, p.last_name, field_name="Last Name")
            filled_last = True
        except FieldNotFoundError:
            pass

        if not (filled_first and filled_last):
            try:
                await self.safe_fill_with_fallbacks(self.FULL_NAME_SELECTORS, p.full_name, field_name="Full Name")
            except FieldNotFoundError:
                if not (filled_first or filled_last):
                    self.mark_failed("Full Name / First Name")

        # 2. Email
        try:
            await self.safe_fill_with_fallbacks(self.EMAIL_SELECTORS, p.email, field_name="Email")
        except FieldNotFoundError:
            self.mark_failed("Email")

        # 3. Phone
        if p.phone:
            try:
                await self.safe_fill_with_fallbacks(self.PHONE_SELECTORS, p.phone, field_name="Phone")
            except FieldNotFoundError:
                self.mark_skipped("Phone (selector not matched)")
        else:
            self.mark_skipped("Phone (not provided)")

        # 4. Location
        if p.location:
            try:
                await self.safe_fill_with_fallbacks(self.LOCATION_SELECTORS, p.location, field_name="Location")
            except FieldNotFoundError:
                self.mark_skipped("Location (selector not matched)")
        else:
            self.mark_skipped("Location (not provided)")

        # 5. LinkedIn
        if p.linkedin_url:
            val = self.validate_url_field(p.linkedin_url, "LinkedIn")
            if val:
                try:
                    await self.safe_fill_with_fallbacks(self.LINKEDIN_SELECTORS, val, field_name="LinkedIn")
                except FieldNotFoundError:
                    self.mark_skipped("LinkedIn (selector not matched)")
        else:
            self.mark_skipped("LinkedIn (not provided)")

        # 6. GitHub
        if p.github_url:
            val = self.validate_url_field(p.github_url, "GitHub")
            if val:
                try:
                    await self.safe_fill_with_fallbacks(self.GITHUB_SELECTORS, val, field_name="GitHub")
                except FieldNotFoundError:
                    self.mark_skipped("GitHub (selector not matched)")
        else:
            self.mark_skipped("GitHub (not provided)")

        # 7. Portfolio / Website
        if p.website:
            val = self.validate_url_field(p.website, "Website")
            if val:
                try:
                    await self.safe_fill_with_fallbacks(self.WEBSITE_SELECTORS, val, field_name="Website")
                except FieldNotFoundError:
                    self.mark_skipped("Website (selector not matched)")
        else:
            self.mark_skipped("Website (not provided)")

        # 8. Resume Upload
        if self.candidate.resume_file_path:
            uploaded = False
            for sel in self.RESUME_SELECTORS:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0:
                        await self.safe_upload_file(sel, self.candidate.resume_file_path)
                        uploaded = True
                        break
                except Exception:
                    continue
            if not uploaded:
                self.mark_skipped("Resume Upload (file input not matched)")
        else:
            self.mark_skipped("Resume Upload (no file path)")

        # 9. Cover Letter
        cover_text = self.candidate.cover_letter or (
            f"Dear Hiring Team,\n\nI am writing to express my strong enthusiasm for this position. "
            f"With extensive background in {', '.join(self.candidate.skills[:4]) or 'software engineering'}, "
            f"I am eager to contribute my skills and experience to your mission.\n\nSincerely,\n{p.full_name}"
        )
        try:
            await self.safe_fill_with_fallbacks(self.COVER_LETTER_SELECTORS, cover_text, field_name="Cover Letter")
        except FieldNotFoundError:
            self.mark_skipped("Cover Letter (no textarea found)")

        # 10. Work Authorization & Custom Q&A
        await self.fill_work_authorization()
        await self.fill_demographics()
        await self.fill_custom_answers()

        # Final halt — NEVER auto-submits
        await self.halt_for_review()

        return self.get_result()
