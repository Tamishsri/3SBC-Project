"""Unit tests for the live CAPTCHA & bot challenge detector."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.captcha_detector import detect_captcha, handle_captcha_challenge


@pytest.mark.asyncio
async def test_detect_cloudflare_turnstile():
    """Detects Cloudflare Turnstile iframe signature."""
    mock_page = MagicMock()
    mock_page.title = AsyncMock(return_value="Job Application | Stripe")

    mock_loc = MagicMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.first = MagicMock()
    mock_loc.first.is_visible = AsyncMock(return_value=True)

    def locator_side_effect(sel):
        if "challenges.cloudflare.com" in sel:
            return mock_loc
        empty_loc = MagicMock()
        empty_loc.count = AsyncMock(return_value=0)
        return empty_loc

    mock_page.locator.side_effect = locator_side_effect

    detected = await detect_captcha(mock_page)
    assert detected == "Cloudflare Turnstile"


@pytest.mark.asyncio
async def test_detect_recaptcha():
    """Detects Google reCAPTCHA signature."""
    mock_page = MagicMock()
    mock_page.title = AsyncMock(return_value="Apply - TechCorp")

    mock_loc = MagicMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.first = MagicMock()
    mock_loc.first.is_visible = AsyncMock(return_value=True)

    def locator_side_effect(sel):
        if "recaptcha" in sel:
            return mock_loc
        empty_loc = MagicMock()
        empty_loc.count = AsyncMock(return_value=0)
        return empty_loc

    mock_page.locator.side_effect = locator_side_effect

    detected = await detect_captcha(mock_page)
    assert detected == "Google reCAPTCHA"


@pytest.mark.asyncio
async def test_detect_challenge_page_title():
    """Detects bot challenge page by title keywords."""
    mock_page = MagicMock()
    mock_page.title = AsyncMock(return_value="Just a moment... | Cloudflare")

    detected = await detect_captcha(mock_page)
    assert detected == "Cloudflare / Bot Challenge Page"


@pytest.mark.asyncio
async def test_detect_clear_page():
    """Returns None when no challenge is detected."""
    mock_page = MagicMock()
    mock_page.title = AsyncMock(return_value="Senior Engineer Application - Stripe")
    empty_loc = MagicMock()
    empty_loc.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = empty_loc

    detected = await detect_captcha(mock_page)
    assert detected is None


@pytest.mark.asyncio
async def test_handle_captcha_returns_true_when_clear():
    """When no captcha is active, handle_captcha_challenge returns True immediately."""
    mock_page = MagicMock()
    mock_page.title = AsyncMock(return_value="Application Form")
    empty_loc = MagicMock()
    empty_loc.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = empty_loc

    result = await handle_captcha_challenge(mock_page, timeout_seconds=1.0)
    assert result is True
