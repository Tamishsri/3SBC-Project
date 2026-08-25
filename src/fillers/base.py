"""Abstract base class for ATS form fillers.

Every ATS-specific filler inherits from ATSFormFiller and implements
the detect() and fill() methods. The base class provides safe field
filling utilities with strict error handling.

CRITICAL: No filler may ever click the Submit/Apply button.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Error as PlaywrightError

from src.exceptions import FieldNotFoundError, ResumeUploadError
from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


class ATSFormFiller(ABC):
    """Abstract base class for all ATS platform form fillers.
    
    Subclasses must implement:
        - platform_name: class variable identifying the ATS
        - detect(): check if the current page matches this ATS
        - fill(): fill all known fields on the form
    
    The base class provides safe_fill_field() and safe_upload_file()
    which handle all error cases explicitly.
    """

    platform_name: str = "Unknown ATS"

    def __init__(self, page: Page, candidate: CandidateData) -> None:
        self.page = page
        self.candidate = candidate
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

    async def safe_fill_field(
        self,
        locator: Locator,
        value: str | None,
        field_name: str,
        *,
        timeout_ms: int = 3000,
        clear_first: bool = True,
    ) -> bool:
        """Safely fill a single form field with strict error handling.
        
        Args:
            locator: Playwright locator for the target input element.
            value: The value to type into the field. If None, field is skipped.
            field_name: Human-readable name for logging (e.g., 'Email').
            timeout_ms: Max wait time in milliseconds for the element.
            clear_first: Whether to clear existing field content before typing.
            
        Returns:
            True if field was filled successfully, False otherwise.
        """
        # Skip if no data available for this field
        if value is None or value.strip() == "":
            self.logger.info(
                "⏭  Skipping '%s' — no data available in candidate profile",
                field_name,
            )
            self._skipped_fields.append(field_name)
            return False

        try:
            # Wait for element with strict timeout
            await locator.wait_for(state="visible", timeout=timeout_ms)
            
            if clear_first:
                await locator.clear()
            
            await locator.fill(value)
            
            self.logger.info("✅ Filled '%s' successfully", field_name)
            self._filled_fields.append(field_name)
            return True

        except PlaywrightTimeoutError:
            self.logger.error(
                "❌ FIELD NOT FOUND: '%s' on %s form. "
                "The element was not visible within %dms. "
                "The page layout may have changed.",
                field_name,
                self.platform_name,
                timeout_ms,
            )
            self._failed_fields.append(field_name)
            return False

        except PlaywrightError as exc:
            self.logger.error(
                "❌ ELEMENT ERROR: '%s' on %s form. "
                "Playwright error: %s",
                field_name,
                self.platform_name,
                exc.message,
            )
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
        
        Args:
            locators: List of Playwright locators to try, in priority order.
            value: The value to fill.
            field_name: Human-readable field name.
            timeout_ms: Timeout per locator attempt.
            
        Returns:
            True if any locator succeeded.
        """
        if value is None or value.strip() == "":
            self.logger.info(
                "⏭  Skipping '%s' — no data available", field_name
            )
            self._skipped_fields.append(field_name)
            return False

        selectors_tried: list[str] = []

        for i, locator in enumerate(locators, 1):
            try:
                await locator.wait_for(state="visible", timeout=timeout_ms)
                await locator.clear()
                await locator.fill(value)
                self.logger.info(
                    "✅ Filled '%s' successfully (locator %d/%d)",
                    field_name, i, len(locators),
                )
                self._filled_fields.append(field_name)
                return True
            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                selector_repr = str(locator)
                selectors_tried.append(selector_repr)
                self.logger.debug(
                    "   Locator %d/%d failed for '%s': %s",
                    i, len(locators), field_name, exc,
                )
                continue

        # All locators failed
        self.logger.error(
            "❌ ALL LOCATORS FAILED for '%s' on %s. "
            "Tried %d selector(s). The page layout may have changed.",
            field_name,
            self.platform_name,
            len(locators),
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
            self.logger.info(
                "⏭  Skipping '%s' upload — no file path provided", field_name
            )
            self._skipped_fields.append(field_name)
            return False

        # Verify file exists locally
        path = Path(file_path)
        if not path.is_file():
            self.logger.error(
                "❌ FILE NOT FOUND: Cannot upload '%s' — file does not exist: %s",
                field_name,
                file_path,
            )
            self._failed_fields.append(field_name)
            return False

        try:
            await locator.wait_for(state="attached", timeout=timeout_ms)
            await locator.set_input_files(str(path))
            self.logger.info("✅ Uploaded '%s': %s", field_name, path.name)
            self._filled_fields.append(field_name)
            return True

        except PlaywrightTimeoutError:
            self.logger.error(
                "❌ UPLOAD FIELD NOT FOUND: '%s' on %s form. "
                "The file input was not found within %dms.",
                field_name,
                self.platform_name,
                timeout_ms,
            )
            self._failed_fields.append(field_name)
            return False

        except PlaywrightError as exc:
            self.logger.error(
                "❌ UPLOAD FAILED: '%s' on %s form. Error: %s",
                field_name,
                self.platform_name,
                exc.message,
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
        
        Args:
            locator: Playwright locator for the select element.
            value: Option value or label to select.
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
            await locator.select_option(label=value)
            self.logger.info("✅ Selected '%s' for '%s'", value, field_name)
            self._filled_fields.append(field_name)
            return True

        except PlaywrightTimeoutError:
            self.logger.error(
                "❌ DROPDOWN NOT FOUND: '%s' on %s form.",
                field_name, self.platform_name,
            )
            self._failed_fields.append(field_name)
            return False

        except PlaywrightError as exc:
            self.logger.error(
                "❌ SELECT FAILED: '%s' on %s — %s",
                field_name, self.platform_name, exc.message,
            )
            self._failed_fields.append(field_name)
            return False

    def halt_for_review(self) -> FillResult:
        """Halt execution and report results for human review.
        
        This method MUST be called at the end of every fill() implementation.
        It prints a highly visible message and returns the FillResult.
        
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

        # Print a BIG, unmissable halt message
        border = "=" * 70
        self.logger.info("")
        self.logger.info(border)
        self.logger.info("  ⛔  FORM FILLING COMPLETE — HALTING FOR HUMAN REVIEW")
        self.logger.info(border)
        self.logger.info("")
        self.logger.info("  Platform:  %s", self.platform_name)
        self.logger.info("  Page URL:  %s", self.page.url)
        self.logger.info("")

        if self._filled_fields:
            self.logger.info("  ✅ Successfully filled (%d):", len(self._filled_fields))
            for f in self._filled_fields:
                self.logger.info("     • %s", f)

        if self._failed_fields:
            self.logger.warning("")
            self.logger.warning("  ❌ FAILED to fill (%d):", len(self._failed_fields))
            for f in self._failed_fields:
                self.logger.warning("     • %s", f)

        if self._skipped_fields:
            self.logger.info("")
            self.logger.info("  ⏭  Skipped — no data (%d):", len(self._skipped_fields))
            for f in self._skipped_fields:
                self.logger.info("     • %s", f)

        self.logger.info("")
        self.logger.info("  Success rate: %.0f%%", result.success_rate)
        self.logger.info("")
        self.logger.info("  👉 DO NOT close this browser window.")
        self.logger.info("  👉 Review ALL fields carefully, then submit MANUALLY.")
        self.logger.info("")
        self.logger.info(border)

        return result
