"""Abstract base class for ATS form fillers.

Every ATS-specific filler inherits from ATSFormFiller and implements
the detect() and fill() methods. The base class provides safe field
filling utilities with strict error handling, scroll-into-view support,
automatic retry on failure, human-like typing mode, and URL validation.

CRITICAL: No filler may ever click the Submit/Apply button.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Error as PlaywrightError

from src.exceptions import FieldNotFoundError, ResumeUploadError
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)

# Basic URL pattern for validation
_URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def is_valid_url(value: str | None) -> bool:
    """Return True if value looks like a valid HTTP(S) URL."""
    if not value:
        return False
    return bool(_URL_PATTERN.match(value.strip()))


class ATSFormFiller(ABC):
    """Abstract base class for all ATS platform form fillers.

    Subclasses must implement:
        - platform_name: class variable identifying the ATS
        - detect(): check if the current page matches this ATS
        - fill(): fill all known fields on the form

    The base class provides:
        - safe_fill_field() / safe_fill_with_fallbacks() with retry + scroll
        - safe_upload_file() for resume upload
        - safe_select_option() for dropdowns
        - human_type() for human-like keystroke simulation
        - validate_url_field() to validate URLs before filling
        - halt_for_review() — ALWAYS call this at the end of fill()
    """

    platform_name: str = "Unknown ATS"

    def __init__(
        self,
        page: Page,
        candidate: CandidateData,
        *,
        human_mode: bool = False,
        multi_page: bool = False,
    ) -> None:
        self.page = page
        self.candidate = candidate
        self.human_mode = human_mode
        self.multi_page = multi_page
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._filled_fields: list[str] = []
        self._failed_fields: list[str] = []
        self._skipped_fields: list[str] = []

    @abstractmethod
    async def detect(self) -> bool:
        """Return True if this filler matches the current page's ATS platform."""

    @abstractmethod
    async def fill(self) -> FillResult:
        """Fill all known fields on the form.

        MUST call self.halt_for_review() at the end.
        MUST NEVER click any submit/apply button.

        Returns:
            FillResult summarizing what was filled, failed, or skipped.
        """

    # ── Human-like typing ────────────────────────────────────────────────────

    async def human_type(self, locator: Locator, value: str) -> None:
        """Type text character-by-character with random delays.

        Simulates human typing to reduce bot-detection risk on ATS platforms
        that monitor keystroke patterns.

        Args:
            locator: Target input element.
            value: Text to type.
        """
        await locator.click()
        for char in value:
            await locator.press(char)
            # Random delay between 40ms and 180ms per character
            await asyncio.sleep(random.uniform(0.04, 0.18))

    # ── URL validation ────────────────────────────────────────────────────────

    def validate_url_field(self, value: str | None, field_name: str) -> str | None:
        """Validate a URL before filling. Returns value if valid, None otherwise.

        Args:
            value: URL string to validate.
            field_name: Human-readable field name for logging.

        Returns:
            The original value if valid, or None to skip filling.
        """
        if not value:
            return None
        if not is_valid_url(value):
            self.logger.warning(
                "[WARN] Skipping '%s' — value does not look like a valid URL: %s",
                field_name, value,
            )
            self._skipped_fields.append(field_name)
            return None
        return value

    # ── Core fill utilities ───────────────────────────────────────────────────

    async def _scroll_to_element(self, locator: Locator) -> None:
        """Scroll an element into view before interacting with it."""
        try:
            await locator.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass  # Non-fatal — proceed anyway

    async def safe_fill_field(
        self,
        locator: Locator,
        value: str | None,
        field_name: str,
        *,
        timeout_ms: int = 3000,
        clear_first: bool = True,
    ) -> bool:
        """Safely fill a single form field with scroll + retry + human mode.

        Args:
            locator: Playwright locator for the target input element.
            value: The value to type into the field. If None, field is skipped.
            field_name: Human-readable name for logging (e.g., 'Email').
            timeout_ms: Max wait time in milliseconds for the element.
            clear_first: Whether to clear existing field content before typing.

        Returns:
            True if field was filled successfully, False otherwise.
        """
        if value is None or value.strip() == "":
            self.logger.info("[SKIP] '%s' - no data available", field_name)
            self._skipped_fields.append(field_name)
            return False

        for attempt in range(1, 3):  # max 2 attempts
            try:
                await locator.wait_for(state="visible", timeout=timeout_ms)
                await self._scroll_to_element(locator)

                if clear_first:
                    await locator.clear()

                if self.human_mode:
                    await self.human_type(locator, value)
                else:
                    await locator.fill(value)

                self.logger.info("[OK] Filled '%s'", field_name)
                self._filled_fields.append(field_name)
                return True

            except PlaywrightTimeoutError:
                if attempt == 1:
                    self.logger.debug("Retrying '%s' after scroll...", field_name)
                    await self._scroll_to_element(locator)
                    continue
                self.logger.error(
                    "[FAIL] FIELD NOT FOUND: '%s' on %s form. "
                    "Not visible within %dms. Page layout may have changed.",
                    field_name, self.platform_name, timeout_ms,
                )
                self._failed_fields.append(field_name)
                return False

            except PlaywrightError as exc:
                self.logger.error(
                    "[FAIL] ELEMENT ERROR: '%s' on %s form. Error: %s",
                    field_name, self.platform_name, exc.message,
                )
                self._failed_fields.append(field_name)
                return False

        self._failed_fields.append(field_name)
        return False

    async def _screenshot_on_failure(self, field_name: str) -> None:
        """Take a screenshot immediately when a field fails.

        Saves to screenshots/fail_<field>_<timestamp>.png.
        Helps debug selector drift after ATS UI changes.

        Args:
            field_name: Name of the field that failed (used in filename).
        """
        from pathlib import Path as _Path
        from datetime import datetime as _dt
        import re as _re

        safe_name = _re.sub(r"[^\w]", "_", field_name.lower())
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        shots_dir = _Path("screenshots") / "failures"
        shots_dir.mkdir(parents=True, exist_ok=True)
        shot_path = shots_dir / f"fail_{safe_name}_{ts}.png"

        try:
            await self.page.screenshot(path=str(shot_path), full_page=True)
            self.logger.warning("[SNAPSHOT] Failure screenshot saved: %s", shot_path)
        except Exception as exc:
            self.logger.debug("Could not take failure screenshot: %s", exc)

    async def safe_fill_with_fallbacks(
        self,
        locators: list[Locator],
        value: str | None,
        field_name: str,
        *,
        timeout_ms: int = 3000,
    ) -> bool:
        """Try multiple locators in order until one succeeds.

        Each locator attempt includes scroll-into-view. If all fail,
        logs a specific error identifying the field and platform.

        Args:
            locators: List of Playwright locators to try, in priority order.
            value: The value to fill.
            field_name: Human-readable field name.
            timeout_ms: Timeout per locator attempt.

        Returns:
            True if any locator succeeded.
        """
        if value is None or value.strip() == "":
            self.logger.info("[SKIP] '%s' - no data available", field_name)
            self._skipped_fields.append(field_name)
            return False

        for i, locator in enumerate(locators, 1):
            try:
                await locator.wait_for(state="visible", timeout=timeout_ms)
                await self._scroll_to_element(locator)
                await locator.clear()

                if self.human_mode:
                    await self.human_type(locator, value)
                else:
                    await locator.fill(value)

                self.logger.info("[OK] Filled '%s' (selector %d/%d)", field_name, i, len(locators))
                self._filled_fields.append(field_name)
                return True

            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                self.logger.debug(
                    "   Selector %d/%d failed for '%s': %s", i, len(locators), field_name, exc,
                )
                continue

        self.logger.error(
            "[FAIL] ALL %d SELECTORS FAILED for '%s' on %s. Page layout may have changed.",
            len(locators), field_name, self.platform_name,
        )
        self._failed_fields.append(field_name)
        # Take immediate screenshot to capture the page state at point of failure
        await self._screenshot_on_failure(field_name)
        return False

    async def safe_upload_file(
        self,
        locator: Locator,
        file_path: str | None,
        field_name: str,
        *,
        timeout_ms: int = 5000,
    ) -> bool:
        """Safely upload a file to a form field.

        Args:
            locator: Playwright locator for the file input element.
            file_path: Absolute path to the file to upload.
            field_name: Human-readable name (e.g., 'Resume').
            timeout_ms: Max wait time for the file input element.

        Returns:
            True if upload was successful.
        """
        if file_path is None:
            self.logger.info("[SKIP] '%s' upload - no file path provided", field_name)
            self._skipped_fields.append(field_name)
            return False

        path = Path(file_path)
        if not path.is_file():
            self.logger.error(
                "[FAIL] FILE NOT FOUND: '%s' does not exist: %s", field_name, file_path,
            )
            self._failed_fields.append(field_name)
            return False

        try:
            await locator.wait_for(state="attached", timeout=timeout_ms)
            await locator.set_input_files(str(path))
            self.logger.info("[OK] Uploaded '%s': %s", field_name, path.name)
            self._filled_fields.append(field_name)
            return True

        except PlaywrightTimeoutError:
            self.logger.error(
                "[FAIL] UPLOAD FIELD NOT FOUND: '%s' on %s form (timeout %dms).",
                field_name, self.platform_name, timeout_ms,
            )
            self._failed_fields.append(field_name)
            return False

        except PlaywrightError as exc:
            self.logger.error(
                "[FAIL] UPLOAD FAILED: '%s' on %s. Error: %s",
                field_name, self.platform_name, exc.message,
            )
            self._failed_fields.append(field_name)
            return False

    async def safe_select_option(
        self,
        locator: Locator,
        value: str | None,
        field_name: str,
        *,
        timeout_ms: int = 3000,
    ) -> bool:
        """Safely select an option from a dropdown.

        Attempts selection by label first, then by value, to handle
        different implementations across ATS platforms.

        Args:
            locator: Playwright locator for the select element.
            value: Option label or value to select.
            field_name: Human-readable name.
            timeout_ms: Max wait time.

        Returns:
            True if selection was successful.
        """
        if value is None:
            self._skipped_fields.append(field_name)
            return False

        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
            await self._scroll_to_element(locator)

            # Try by label first, then by value
            try:
                await locator.select_option(label=value)
            except PlaywrightError:
                await locator.select_option(value=value)

            self.logger.info("[OK] Selected '%s' for '%s'", value, field_name)
            self._filled_fields.append(field_name)
            return True

        except PlaywrightTimeoutError:
            self.logger.error("[FAIL] DROPDOWN NOT FOUND: '%s' on %s.", field_name, self.platform_name)
            self._failed_fields.append(field_name)
            return False

        except PlaywrightError as exc:
            self.logger.error(
                "[FAIL] SELECT FAILED: '%s' on %s - %s", field_name, self.platform_name, exc.message,
            )
            self._failed_fields.append(field_name)
            return False

    async def safe_set_choice(
        self,
        question_keywords: list[str],
        target_value: str | None,
        field_name: str,
    ) -> bool:
        """Find a question container by keywords and select matching option or radio button.

        Args:
            question_keywords: Substrings identifying the question.
            target_value: Option text or value to select (e.g. 'Yes', 'No', 'Decline').
            field_name: Human-readable field name for reporting.

        Returns:
            True if matched and selected successfully.
        """
        if not target_value or not target_value.strip():
            return False

        target_norm = target_value.strip().lower()

        # Strategy 1: Look for select elements inside matching question blocks
        for kw in question_keywords:
            try:
                # Find select associated with label/fieldset
                selectors = [
                    f'label:has-text("{kw}") >> select',
                    f'fieldset:has-text("{kw}") >> select',
                    f'div:has-text("{kw}") >> select',
                ]
                for sel in selectors:
                    locator = self.page.locator(sel).first
                    if await locator.count() > 0:
                        await self._scroll_to_element(locator)
                        # Try selecting by label first, then value
                        try:
                            await locator.select_option(label=target_value, timeout=2000)
                            self.logger.info("[OK] Selected '%s' for '%s'", target_value, field_name)
                            self._filled_fields.append(field_name)
                            return True
                        except Exception:
                            # Try selecting by case-insensitive partial match on options
                            opts = await locator.locator("option").all_inner_texts()
                            for opt in opts:
                                if target_norm in opt.lower():
                                    await locator.select_option(label=opt, timeout=2000)
                                    self.logger.info("[OK] Selected '%s' for '%s'", opt.strip(), field_name)
                                    self._filled_fields.append(field_name)
                                    return True
            except Exception:
                continue

        # Strategy 2: Look for radio buttons or checkboxes matching the target value INSIDE question container
        for kw in question_keywords:
            try:
                radio_sel = [
                    f'fieldset:has-text("{kw}") input[type="radio"][value*="{target_value}" i]',
                    f'fieldset:has-text("{kw}") label:has-text("{target_value}") >> input[type="radio"]',
                    f'fieldset:has-text("{kw}") label:has-text("{target_value}") input[type="radio"]',
                    f'div:has-text("{kw}") input[type="radio"][value*="{target_value}" i]',
                    f'div:has-text("{kw}") label:has-text("{target_value}") >> input[type="radio"]',
                    f'div:has-text("{kw}") label:has-text("{target_value}") input[type="radio"]',
                    f'section:has-text("{kw}") input[type="radio"][value*="{target_value}" i]',
                    f'section:has-text("{kw}") label:has-text("{target_value}") >> input[type="radio"]',
                ]
                for r_sel in radio_sel:
                    radio = self.page.locator(r_sel).first
                    if await radio.count() > 0:
                        await self._scroll_to_element(radio)
                        try:
                            await radio.check(force=True, timeout=2000)
                        except Exception:
                            await radio.click(force=True, timeout=2000)
                        self.logger.info("[OK] Checked radio '%s' for '%s'", target_value, field_name)
                        self._filled_fields.append(field_name)
                        return True
            except Exception:
                continue

        return False

    async def fill_compliance_and_work_auth(self) -> None:
        """Fill standard work authorization and EEOC demographic questions if present."""
        auth = self.candidate.work_authorization
        demo = self.candidate.demographics

        self.logger.info("--- Checking Standard Work Authorization & Compliance Questions ---")

        # 1. Legal Work Authorization
        auth_val = "Yes" if auth.authorized_to_work else "No"
        await self.safe_set_choice(
            ["authorized to work", "legally authorized", "eligible to work", "work authorization"],
            auth_val,
            "Work Authorization",
        )

        # 2. Visa Sponsorship
        spon_val = "Yes" if auth.requires_sponsorship else "No"
        await self.safe_set_choice(
            ["require sponsorship", "visa sponsorship", "need sponsorship", "require a visa"],
            spon_val,
            "Visa Sponsorship",
        )

        # 3. Gender
        if demo.gender:
            await self.safe_set_choice(["gender", "sex"], demo.gender, "EEOC Gender")

        # 4. Race / Ethnicity
        if demo.race_ethnicity:
            await self.safe_set_choice(["race", "ethnicity", "hispanic"], demo.race_ethnicity, "EEOC Race/Ethnicity")

        # 5. Veteran Status
        if demo.veteran_status:
            await self.safe_set_choice(["veteran", "military"], demo.veteran_status, "EEOC Veteran Status")

        # 6. Disability Status
        if demo.disability_status:
            await self.safe_set_choice(["disability", "disabled"], demo.disability_status, "EEOC Disability Status")

    async def fill_custom_questions(self) -> None:
        """Fill company-specific custom questions from candidate data and custom_answers map."""
        auth = self.candidate.work_authorization
        custom_map = self.candidate.custom_answers.copy()

        # Add standard parameters to custom mapping
        if auth.notice_period_days is not None:
            custom_map["notice period"] = str(auth.notice_period_days)
        if auth.expected_salary:
            custom_map["expected salary"] = auth.expected_salary
            custom_map["desired compensation"] = auth.expected_salary

        if not custom_map:
            return

        self.logger.info("--- Checking Dynamic Custom Company Questions ---")

        for key, val in custom_map.items():
            if not val or not str(val).strip():
                continue

            field_label = f"Custom Q: {key.title()}"
            val_str = str(val).strip()

            # Try finding text input or textarea by label text or placeholder
            selectors = [
                f'label:has-text("{key}") >> input[type="text"]',
                f'label:has-text("{key}") >> input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])',
                f'label:has-text("{key}") >> textarea',
                f'input[placeholder*="{key}" i]',
                f'textarea[placeholder*="{key}" i]',
            ]
            for sel in selectors:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0:
                        await self._scroll_to_element(loc)
                        if self.human_mode:
                            await self.human_type(loc, val_str)
                        else:
                            await loc.fill(val_str)
                        self.logger.info("[OK] Filled custom question '%s': %s", key, val_str)
                        self._filled_fields.append(field_label)
                        break
                except Exception:
                    continue

    async def advance_to_next_wizard_page(self) -> bool:
        """Advance to next wizard step on multi-page forms, ensuring NEVER to click final submit.

        Returns:
            True if advanced to next page, False if at final review screen or no next button.
        """
        if not self.multi_page:
            return False

        next_selectors = [
            'button:has-text("Next"):not(:has-text("Submit")):not(:has-text("Apply"))',
            'button:has-text("Continue"):not(:has-text("Submit")):not(:has-text("Apply"))',
            'button:has-text("Save and Continue")',
            'button:has-text("Save & Continue")',
            '[data-automation-id="bottom-navigation-next-button"]',
        ]

        for sel in next_selectors:
            try:
                btn = self.page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    btn_text = (await btn.inner_text()).lower()
                    # SAFETY GUARD: Strict check — Never auto-submit!
                    if any(term in btn_text for term in ["submit", "apply", "finish", "send application"]):
                        self.logger.info("[STOP] Final submission button detected ('%s'). Halting for human review.", btn_text)
                        return False

                    self.logger.info("[WIZARD] Advancing to next step: Clicking '%s'...", btn_text.strip())
                    await self._scroll_to_element(btn)
                    await btn.click()
                    # Wait for navigation/SPA state
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        await asyncio.sleep(2.0)
                    return True
            except Exception:
                continue

        return False

    async def detect_next_page(self) -> bool:
        """Check if the form has a 'Next' or 'Continue' button (multi-page form).

        Returns:
            True if a next-page button is found (logs a prominent warning).
        """
        next_selectors = [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Next Step")',
            '[type="submit"]:has-text("Next")',
        ]
        for sel in next_selectors:
            try:
                count = await self.page.locator(sel).count()
                if count > 0:
                    self.logger.warning(
                        "[!!] MULTI-PAGE FORM: A 'Next/Continue' button was found. "
                        "Run with --multi-page to auto-advance through wizard steps."
                    )
                    return True
            except Exception:
                continue
        return False

    # ── Halt and report ───────────────────────────────────────────────────────

    def halt_for_review(self) -> FillResult:
        """Halt execution and report results for human review.

        MUST be called at the end of every fill() implementation.
        Prints a highly visible halt message and returns FillResult.

        Returns:
            FillResult summarizing the fill operation.
        """
        result = FillResult(
            ats_platform=self.platform_name,
            page_url=self.page.url,
            filled_fields=self._filled_fields.copy(),
            failed_fields=self._failed_fields.copy(),
            skipped_fields=self._skipped_fields.copy(),
        )

        border = "=" * 70
        self.logger.info("")
        self.logger.info(border)
        self.logger.info("  [HALT] FORM FILLING COMPLETE - AWAITING HUMAN REVIEW")
        self.logger.info(border)
        self.logger.info("")
        self.logger.info("  Platform:     %s", self.platform_name)
        self.logger.info("  Page URL:     %s", self.page.url)
        self.logger.info("  Human Mode:   %s", "ON" if self.human_mode else "OFF")
        self.logger.info("")

        if self._filled_fields:
            self.logger.info("  [OK] Successfully filled (%d):", len(self._filled_fields))
            for f in self._filled_fields:
                self.logger.info("     - %s", f)

        if self._failed_fields:
            self.logger.warning("")
            self.logger.warning("  [!!] FAILED to fill (%d):", len(self._failed_fields))
            for f in self._failed_fields:
                self.logger.warning("     - %s", f)

        if self._skipped_fields:
            self.logger.info("")
            self.logger.info("  [--] Skipped - no data (%d):", len(self._skipped_fields))
            for f in self._skipped_fields:
                self.logger.info("     - %s", f)

        self.logger.info("")
        self.logger.info("  Success rate: %.0f%%", result.success_rate)
        self.logger.info("")
        self.logger.info("  >>> DO NOT close this browser window.")
        self.logger.info("  >>> Review ALL fields carefully, then submit MANUALLY.")
        self.logger.info("")
        self.logger.info(border)

        return result
