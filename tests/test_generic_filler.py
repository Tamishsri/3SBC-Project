"""Unit tests for the GenericAdaptiveFiller and unlisted ATS web form automation."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.ats_router import get_filler
from src.exceptions import UnsupportedATSError
from src.fillers.generic import GenericAdaptiveFiller
from src.models import CandidateData, PersonalInfo


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+919876543210",
            location="Chennai, India",
            linkedin_url="https://linkedin.com/in/tamishsri",
        ),
        skills=["Python", "Playwright", "FastAPI"],
    )


@pytest.mark.asyncio
async def test_generic_filler_detects_standard_form():
    """Detects page when standard input elements and form tags are present."""
    mock_page = MagicMock()
    mock_page.url = "https://jobs.ashbyhq.com/company/123"

    async def mock_count():
        return 1

    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(side_effect=mock_count)
    mock_page.locator.return_value = mock_locator

    candidate = CandidateData(
        personal=PersonalInfo(first_name="Tamish", last_name="Sridatta", email="tamish@example.com")
    )
    filler = GenericAdaptiveFiller(mock_page, candidate)
    detected = await filler.detect()
    assert detected is True


@pytest.mark.asyncio
async def test_generic_filler_detects_false_on_blank():
    """Returns False if no form or input markers exist."""
    mock_page = MagicMock()
    mock_page.url = "https://example.com/about-us"

    async def mock_zero_count():
        return 0

    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(side_effect=mock_zero_count)
    mock_page.locator.return_value = mock_locator

    candidate = CandidateData(
        personal=PersonalInfo(first_name="Tamish", last_name="Sridatta", email="tamish@example.com")
    )
    filler = GenericAdaptiveFiller(mock_page, candidate)
    detected = await filler.detect()
    assert detected is False


@pytest.mark.asyncio
async def test_ats_router_falls_back_to_generic_when_enabled(sample_candidate):
    """When allow_generic=True, router falls back to GenericAdaptiveFiller on unknown ATS."""
    mock_page = MagicMock()
    mock_page.url = "https://customcareers.techcorp.io/apply"

    def mock_locator_fn(selector):
        loc = MagicMock()
        if any(ats in selector.lower() for ats in ["greenhouse", "lever", "workday", "smartrecruiters", "iframe", "grnhse", "postings"]):
            loc.count = AsyncMock(return_value=0)
        else:
            loc.count = AsyncMock(return_value=1)
        return loc

    mock_page.locator.side_effect = mock_locator_fn

    filler = await get_filler(mock_page, sample_candidate, allow_generic=True)
    assert isinstance(filler, GenericAdaptiveFiller)
    assert filler.platform_name == "Generic Web Form"


@pytest.mark.asyncio
async def test_ats_router_raises_unsupported_when_generic_disabled(sample_candidate):
    """When allow_generic=False (default), router raises UnsupportedATSError on unknown domains."""
    mock_page = MagicMock()
    mock_page.url = "https://unknown-domain-xyz.com/careers"
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = mock_locator

    with pytest.raises(UnsupportedATSError):
        await get_filler(mock_page, sample_candidate, allow_generic=False)
