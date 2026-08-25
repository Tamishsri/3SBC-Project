"""Unit tests for the backend API client."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from src.api_client import fetch_candidate_data, load_candidate_from_file
from src.config import Config
from src.exceptions import APIConnectionError, DataValidationError


@pytest.fixture
def test_config():
    return Config(
        api_base_url="http://mock-api:8000",
        api_token="test-token-xyz",
        browser_debug_port=9222,
        log_level="INFO",
    )


@pytest.fixture
def valid_candidate_json():
    return {
        "personal": {
            "first_name": "Tamish",
            "last_name": "Sridatta",
            "email": "tamish@example.com",
            "phone": "+91-9876543210",
        },
        "skills": ["Python", "Playwright"],
    }


@pytest.mark.asyncio
async def test_fetch_candidate_data_success(test_config, valid_candidate_json):
    """Test successful candidate data fetch and validation."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = valid_candidate_json

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        candidate = await fetch_candidate_data(123, test_config)

        assert candidate.personal.first_name == "Tamish"
        assert candidate.personal.email == "tamish@example.com"
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-token-xyz"


@pytest.mark.asyncio
async def test_fetch_candidate_data_401_unauthorized(test_config):
    """Test 401 raises APIConnectionError with clear detail."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(APIConnectionError) as exc_info:
            await fetch_candidate_data(123, test_config)

        assert "Authentication failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_candidate_data_404_not_found(test_config):
    """Test 404 candidate not found."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(APIConnectionError) as exc_info:
            await fetch_candidate_data(999, test_config)

        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_fetch_candidate_data_invalid_schema(test_config):
    """Test data validation failure when required fields are absent."""
    invalid_data = {
        "personal": {
            "first_name": "Tamish"
            # Missing last_name and email
        }
    }
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = invalid_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(DataValidationError) as exc_info:
            await fetch_candidate_data(123, test_config)

        assert "Candidate data validation failed" in str(exc_info.value)


def test_load_candidate_from_file():
    """Test loading candidate data from local JSON file."""
    candidate = load_candidate_from_file("sample_candidate.json")
    assert candidate.personal.first_name == "Tamish"
    assert candidate.personal.email == "tamish.sridatta@example.com"
    assert len(candidate.experience) > 0
