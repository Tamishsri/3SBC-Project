"""Unit tests for ATS Form Filler v2.8 Usability & Form Resilience features.

Tests cover:
1. Smart Numeric & Currency Sanitizer (clean_numeric_input in normalizer.py)
2. Resilient Fuzzy Dropdown Option Matcher (safe_select_option in fillers/base.py)
3. In-Browser Visual Field Highlighting & Review Badge (inject_review_overlay in fillers/base.py)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from playwright.async_api import Error as PlaywrightError

from src.models import CandidateData, FillResult, PersonalInfo
from src.normalizer import clean_numeric_input
from src.fillers.base import ATSFormFiller


# ═══════════════════════════════════════════════════════════════════════════
# 1. Numeric & Currency Sanitizer Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanNumericInput:
    """Test suite for clean_numeric_input() in normalizer.py."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("$120,000", "120000"),
            ("$120,000/yr", "120000"),
            ("120k", "120000"),
            ("120K", "120000"),
            ("85.5k", "85500"),
            ("1.5M", "1500000"),
            ("2m", "2000000"),
            ("€85,000", "85000"),
            ("£65,000", "65000"),
            ("₹15,00,000", "1500000"),
            ("¥500,000", "500000"),
            ("30 days", "30"),
            ("2 weeks", "2"),
            ("5 years", "5"),
            ("40 hours/week", "40"),
            ("3.85 GPA", "3.85"),
            ("3.9/4.0", "3.9"),
            ("100", "100"),
            ("0", "0"),
            ("  95,000  ", "95000"),
            ("125000.50", "125000.50"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_clean_numeric_input_variations(self, raw: str | None, expected: str):
        assert clean_numeric_input(raw) == expected

    def test_clean_numeric_non_numeric_fallback(self):
        # When no numeric characters exist, return empty string for numeric fields
        assert clean_numeric_input("immediate") == ""
        assert clean_numeric_input("Negotiable") == ""


# ═══════════════════════════════════════════════════════════════════════════
# 2. Resilient Fuzzy Dropdown Option Matcher Tests
# ═══════════════════════════════════════════════════════════════════════════

class ConcreteFiller(ATSFormFiller):
    """Minimal concrete subclass to test ATSFormFiller base methods."""

    @property
    def platform_name(self) -> str:
        return "TestATS"

    async def detect(self) -> bool:
        return True

    async def fill(self) -> FillResult:
        return self.halt_for_review()


@pytest.fixture
def mock_filler():
    mock_page = AsyncMock()
    mock_page.url = "https://jobs.example.com/apply"
    candidate = CandidateData(
        personal=PersonalInfo(
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
            phone="555-123-4567",
            location="San Francisco, CA",
        )
    )
    return ConcreteFiller(page=mock_page, candidate=candidate, human_mode=False)


class TestFuzzyDropdownMatcher:
    """Test suite for safe_select_option() fuzzy fallback."""

    @pytest.mark.asyncio
    async def test_select_option_exact_label_success(self, mock_filler):
        locator = AsyncMock()
        locator.select_option = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.evaluate = AsyncMock()

        success = await mock_filler.safe_select_option(locator, "California", "State")
        assert success is True
        locator.select_option.assert_called_once_with(label="California")
        assert "State" in mock_filler._filled_fields

    @pytest.mark.asyncio
    async def test_select_option_fallback_to_value(self, mock_filler):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.evaluate = AsyncMock()

        # Label fails, value succeeds
        locator.select_option = AsyncMock(
            side_effect=[PlaywrightError("Label not found"), None]
        )

        success = await mock_filler.safe_select_option(locator, "CA", "State")
        assert success is True
        assert locator.select_option.call_count == 2
        locator.select_option.assert_any_call(value="CA")
        assert "State" in mock_filler._filled_fields

    @pytest.mark.asyncio
    async def test_select_option_fuzzy_match_fallback(self, mock_filler):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.evaluate = AsyncMock()

        # Both label and value fail on first try, but fuzzy match finds "United States of America"
        option_loc = AsyncMock()
        option_loc.all_text_contents = AsyncMock(
            return_value=["Please select...", "Canada", "United States of America", "Mexico"]
        )
        locator.locator = MagicMock(return_value=option_loc)

        locator.select_option = AsyncMock(
            side_effect=[
                PlaywrightError("No label United States"),
                PlaywrightError("No value United States"),
                None,  # fuzzy match on 'United States of America' succeeds
            ]
        )

        success = await mock_filler.safe_select_option(locator, "United States", "Country")
        assert success is True
        locator.select_option.assert_called_with(label="United States of America")
        assert "Country" in mock_filler._filled_fields

    @pytest.mark.asyncio
    async def test_select_option_fails_gracefully_when_no_match(self, mock_filler):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()

        option_loc = AsyncMock()
        option_loc.all_text_contents = AsyncMock(return_value=["Engineering", "Design", "Product"])
        locator.locator = MagicMock(return_value=option_loc)

        locator.select_option = AsyncMock(side_effect=PlaywrightError("No match"))

        success = await mock_filler.safe_select_option(locator, "Accounting", "Department")
        assert success is False
        assert "Department" in mock_filler._failed_fields


# ═══════════════════════════════════════════════════════════════════════════
# 3. In-Browser Visual Field Highlighting & Review Badge Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVisualReviewOverlay:
    """Test suite for inject_review_overlay() and halt_for_review()."""

    @pytest.mark.asyncio
    async def test_inject_review_overlay_executes_script(self, mock_filler):
        mock_filler.page.evaluate = AsyncMock(return_value=True)
        mock_filler._filled_fields = ["Full Name", "Email"]
        mock_filler._failed_fields = ["Portfolio"]

        ok = await mock_filler.inject_review_overlay()
        assert ok is True
        mock_filler.page.evaluate.assert_called_once()
        call_arg = mock_filler.page.evaluate.call_args[0][0]
        assert "ats-review-badge" in call_arg
        assert "READY FOR REVIEW" in call_arg
        assert "data-ats-filled" in call_arg

    @pytest.mark.asyncio
    async def test_safe_fill_input_tags_element(self, mock_filler):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.get_attribute = AsyncMock(return_value="text")
        locator.fill = AsyncMock()
        locator.evaluate = AsyncMock()

        success = await mock_filler.safe_fill_field(locator, "Alice Smith", "Full Name")
        assert success is True
        locator.evaluate.assert_called_once_with("el => el.setAttribute('data-ats-filled', 'true')")

    @pytest.mark.asyncio
    async def test_safe_fill_input_auto_sanitizes_number_fields(self, mock_filler):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.get_attribute = AsyncMock(return_value="number")
        locator.fill = AsyncMock()
        locator.evaluate = AsyncMock()

        success = await mock_filler.safe_fill_field(locator, "$135,000", "Desired Salary")
        assert success is True
        # Verify the sanitized numeric string "135000" was passed to fill, NOT "$135,000"
        locator.fill.assert_called_once_with("135000")

    def test_halt_for_review_returns_valid_fill_result(self, mock_filler):
        mock_filler._filled_fields = ["Name", "Email"]
        mock_filler._failed_fields = ["Resume"]
        mock_filler._skipped_fields = ["Website"]

        result = mock_filler.halt_for_review()
        assert isinstance(result, FillResult)
        assert result.ats_platform == "TestATS"
        assert result.filled_fields == ["Name", "Email"]
        assert result.failed_fields == ["Resume"]
        assert result.skipped_fields == ["Website"]
        assert round(result.success_rate, 1) == 66.7
