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

    def __init__(self, page: Page, candidate: CandidateData, *, human_mode: bool = False) -> None:
        self.page = page
        self.candidate = candidate
        self.human_mode = human_mode
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
                        "This filler only handles the FIRST page. Click 'Next' manually "
                        "and re-run for subsequent pages."
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
