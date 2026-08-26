"""Unit tests for the webhook and Slack/Discord notification dispatcher."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.models import CandidateData, PersonalInfo, FillResult
from src.notifier import (
    build_webhook_payload,
    send_fill_notification,
    send_fill_notification_sync,
)


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        )
    )


@pytest.fixture
def sample_fill_result():
    return FillResult(
        ats_platform="Greenhouse",
        page_url="https://boards.greenhouse.io/stripe/jobs/123",
        filled_fields=["First Name", "Last Name", "Email"],
        failed_fields=[],
        skipped_fields=["LinkedIn"],
    )


def test_build_webhook_payload_format(sample_candidate, sample_fill_result):
    """Verify standard schema, Slack block kit, and Discord embed formatting."""
    payload = build_webhook_payload(sample_fill_result, sample_candidate, notes="Test Staging")

    assert payload["event"] == "application_staged"
    assert payload["ats_platform"] == "Greenhouse"
    assert payload["candidate"]["name"] == "Tamish Sridatta"
    assert payload["metrics"]["success_rate_pct"] == 100.0
    assert payload["metrics"]["has_failures"] is False

    # Check Slack compatibility
    assert "text" in payload
    assert "*Candidate:*" in payload["text"]
    assert "blocks" in payload
    assert len(payload["blocks"]) >= 2

    # Check Discord compatibility
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    assert payload["embeds"][0]["color"] == 0x4ADE80  # Green color


@pytest.mark.asyncio
async def test_send_fill_notification_success(sample_candidate, sample_fill_result):
    """Successful 200 HTTP response returns True."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        success = await send_fill_notification(
            webhook_url="https://hooks.slack.com/services/T00/B00/X00",
            result=sample_fill_result,
            candidate=sample_candidate,
        )

        assert success is True
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_send_fill_notification_handles_server_error(sample_candidate, sample_fill_result):
    """500 server error returns False gracefully without throwing an exception."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.is_success = False
    mock_resp.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        success = await send_fill_notification(
            webhook_url="https://hooks.slack.com/error",
            result=sample_fill_result,
            candidate=sample_candidate,
        )

        assert success is False


@pytest.mark.asyncio
async def test_send_fill_notification_handles_timeout(sample_candidate, sample_fill_result):
    """Timeout exception is suppressed and returns False."""
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
        success = await send_fill_notification(
            webhook_url="https://slow-webhook.org/timeout",
            result=sample_fill_result,
            candidate=sample_candidate,
        )
        assert success is False


@pytest.mark.asyncio
async def test_send_fill_notification_invalid_url(sample_candidate, sample_fill_result):
    """Invalid URL scheme is rejected without making network calls."""
    assert await send_fill_notification("ftp://invalid", sample_fill_result, sample_candidate) is False
    assert await send_fill_notification("", sample_fill_result, sample_candidate) is False


def test_send_fill_notification_sync(sample_candidate, sample_fill_result):
    """Synchronous dispatch helper."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True

    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value = mock_resp
        res = send_fill_notification_sync("https://hooks.slack.com/sync", sample_fill_result, sample_candidate)
        assert res is True
