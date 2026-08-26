"""Unit tests for ATS router and platform fillers."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.ats_router import get_filler, register_filler
from src.exceptions import UnsupportedATSError
from src.fillers.base import ATSFormFiller
from src.fillers.greenhouse import GreenhouseFiller
from src.fillers.lever import LeverFiller
from src.models import CandidateData, PersonalInfo


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+91-9876543210",
        )
    )


@pytest.mark.asyncio
async def test_detect_greenhouse(sample_candidate):
    """Test Greenhouse ATS detection from URL."""
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/company/jobs/123456"

    filler = await get_filler(mock_page, sample_candidate)
    assert isinstance(filler, GreenhouseFiller)
    assert filler.platform_name == "Greenhouse"


@pytest.mark.asyncio
async def test_detect_lever(sample_candidate):
    """Test Lever ATS detection from URL."""
    mock_page = MagicMock()
    mock_page.url = "https://jobs.lever.co/company/abcdef-1234-5678"

    filler = await get_filler(mock_page, sample_candidate)
    assert isinstance(filler, LeverFiller)
    assert filler.platform_name == "Lever"


@pytest.mark.asyncio
async def test_detect_workday(sample_candidate):
    """Test Workday ATS detection from URL."""
    mock_page = MagicMock()
    mock_page.url = "https://company.wd3.myworkdayjobs.com/careers/job/123"

    filler = await get_filler(mock_page, sample_candidate)
    assert filler.platform_name == "Workday"


@pytest.mark.asyncio
async def test_unsupported_ats(sample_candidate):
    """Test that unsupported platforms raise UnsupportedATSError."""
    mock_page = MagicMock()
    mock_page.url = "https://icims.com/jobs/company/apply"

    with pytest.raises(UnsupportedATSError) as exc_info:
        await get_filler(mock_page, sample_candidate)

    assert "No form filler available for" in str(exc_info.value)
    assert "Greenhouse" in str(exc_info.value)
    assert "Lever" in str(exc_info.value)
    assert "Workday" in str(exc_info.value)


def test_filler_selectors_structure():
    """Verify that all fillers define required selectors with fallbacks."""
    for filler_cls in [GreenhouseFiller, LeverFiller]:
        assert hasattr(filler_cls, "SELECTORS")
        selectors = filler_cls.SELECTORS
        assert isinstance(selectors, dict)
        for field_name, selector_list in selectors.items():
            assert isinstance(selector_list, list)
            assert len(selector_list) > 0, f"{filler_cls.__name__} has empty selector list for {field_name}"
