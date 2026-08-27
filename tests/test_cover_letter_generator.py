"""Unit tests for the contextual cover letter generator."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.cover_letter_generator import (
    extract_page_job_context,
    generate_contextual_cover_letter,
    augment_candidate_cover_letter,
)
from src.models import CandidateData, PersonalInfo, WorkExperience


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+91-9876543210",
        ),
        skills=["Python", "FastAPI", "Playwright", "Docker"],
        experience=[
            WorkExperience(
                company="3SBC Tech",
                title="Automation Engineer",
                start_date="2022-01",
            )
        ],
    )


def test_generate_contextual_cover_letter(sample_candidate):
    """Verifies that generated letter contains company, role, skills, and experience."""
    letter = generate_contextual_cover_letter(
        candidate=sample_candidate,
        company="Stripe",
        role="Senior Backend Engineer",
    )

    assert "Stripe Hiring Team" in letter
    assert "Senior Backend Engineer" in letter
    assert "Python, FastAPI, Playwright" in letter
    assert "3SBC Tech" in letter
    assert "Tamish Sridatta" in letter
    assert "tamish@example.com" in letter


@pytest.mark.asyncio
async def test_extract_page_job_context():
    """Extracts role and company from page DOM and URL."""
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/456789"
    mock_page.title = AsyncMock(return_value="Staff Infrastructure Engineer - Stripe")

    mock_h1 = MagicMock()
    mock_h1.count = AsyncMock(return_value=1)
    mock_h1.text_content = AsyncMock(return_value="Staff Infrastructure Engineer")
    mock_h1.first = mock_h1

    def locator_side_effect(sel):
        if "meta" in sel:
            empty = MagicMock()
            empty.count = AsyncMock(return_value=0)
            empty.get_attribute = AsyncMock(return_value=None)
            empty.first = empty
            return empty
        return mock_h1

    mock_page.locator.side_effect = locator_side_effect

    context = await extract_page_job_context(mock_page)
    assert "Stripe" in context["company"]
    assert "Staff Infrastructure Engineer" in context["role"]


@pytest.mark.asyncio
async def test_augment_candidate_cover_letter(sample_candidate):
    """Augments candidate with generated letter if empty."""
    mock_page = MagicMock()
    mock_page.url = "https://jobs.lever.co/databricks/12345"
    mock_page.title = AsyncMock(return_value="Data Engineer | Databricks")

    mock_h1 = MagicMock()
    mock_h1.count = AsyncMock(return_value=1)
    mock_h1.text_content = AsyncMock(return_value="Data Engineer")
    mock_h1.first = mock_h1

    def locator_side_effect(sel):
        if "meta" in sel:
            empty = MagicMock()
            empty.count = AsyncMock(return_value=0)
            empty.first = empty
            return empty
        return mock_h1

    mock_page.locator.side_effect = locator_side_effect

    assert sample_candidate.cover_letter is None

    augmented = await augment_candidate_cover_letter(sample_candidate, mock_page)
    assert augmented.cover_letter is not None
    assert "Databricks" in augmented.cover_letter
    assert "Data Engineer" in augmented.cover_letter
