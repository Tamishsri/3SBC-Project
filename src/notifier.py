"""Real-time webhook notification dispatcher.

Sends event notifications to Slack incoming webhooks, Discord webhooks,
Zapier, or custom HTTP endpoints when candidate applications are staged.
All network calls are non-blocking with strict timeouts so failures never
interrupt form filling or batch operations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from src.models import CandidateData, FillResult

logger = logging.getLogger(__name__)


def build_webhook_payload(
    result: FillResult,
    candidate: CandidateData,
    notes: str = "",
) -> dict[str, Any]:
    """Build a rich, multi-platform compatible webhook payload.

    Compatible with Slack, Discord, and generic JSON webhook consumers.
    """
    cand_name = candidate.personal.full_name
    cand_email = candidate.personal.email
    rate_str = f"{result.success_rate:.0f}%"
    filled_count = len(result.filled_fields)
    failed_count = len(result.failed_fields)
    skipped_count = len(result.skipped_fields)
    iso_time = datetime.now().isoformat()

    status_emoji = "✅" if not result.has_failures else "⚠️"
    headline = f"{status_emoji} Application Staged: {cand_name} on {result.ats_platform}"

    # 1. Generic JSON schema
    payload: dict[str, Any] = {
        "event": "application_staged",
        "timestamp": iso_time,
        "ats_platform": result.ats_platform,
        "page_url": result.page_url,
        "candidate": {
            "name": cand_name,
            "email": cand_email,
        },
        "metrics": {
            "success_rate_pct": result.success_rate,
            "fields_filled": filled_count,
            "fields_failed": failed_count,
            "fields_skipped": skipped_count,
            "has_failures": result.has_failures,
        },
        "notes": notes,
    }

    # 2. Slack Block Kit & Text compatibility
    payload["text"] = (
        f"{headline}\n"
        f"• *Candidate:* {cand_name} ({cand_email})\n"
        f"• *Platform:* {result.ats_platform}\n"
        f"• *Success Rate:* {rate_str} ({filled_count} filled, {failed_count} failed)\n"
        f"• *Action Required:* Review staged application before submitting manually."
    )

    payload["blocks"] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": headline,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Candidate:*\n{cand_name}"},
                {"type": "mrkdwn", "text": f"*Platform:*\n{result.ats_platform}"},
                {"type": "mrkdwn", "text": f"*Fill Success:*\n{rate_str}"},
                {"type": "mrkdwn", "text": f"*Fields:*\n{filled_count} filled / {failed_count} failed"},
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Staged at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | *Core Rule:* Never Auto-Submits",
                }
            ],
        },
    ]

    # 3. Discord Embeds compatibility
    discord_color = 0x4ADE80 if not result.has_failures else 0xFACC15
    payload["embeds"] = [
        {
            "title": headline,
            "url": result.page_url if result.page_url.startswith("http") else None,
            "color": discord_color,
            "fields": [
                {"name": "Candidate", "value": cand_name, "inline": True},
                {"name": "Platform", "value": result.ats_platform, "inline": True},
                {"name": "Success Rate", "value": rate_str, "inline": True},
                {
                    "name": "Summary",
                    "value": f"{filled_count} filled, {failed_count} failed, {skipped_count} skipped",
                    "inline": False,
                },
            ],
            "footer": {"text": "ATS Form Filler • Manual Submission Required"},
            "timestamp": iso_time,
        }
    ]

    return payload


async def send_fill_notification(
    webhook_url: str,
    result: FillResult,
    candidate: CandidateData,
    notes: str = "",
    timeout_seconds: float = 3.0,
) -> bool:
    """Send asynchronous webhook notification without blocking the main workflow.

    Args:
        webhook_url: Target webhook HTTP(S) URL.
        result: Completed FillResult.
        candidate: CandidateData applied.
        notes: Optional context string.
        timeout_seconds: Max seconds to wait for webhook response (default: 3.0).

    Returns:
        True if webhook returned 2xx/OK, False otherwise (never raises).
    """
    if not webhook_url or not webhook_url.strip().startswith(("http://", "https://")):
        logger.warning("[WEBHOOK] Invalid webhook URL: %s", webhook_url)
        return False

    payload = build_webhook_payload(result, candidate, notes=notes)

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.is_success or resp.status_code in (200, 201, 204):
                logger.info("[WEBHOOK] Notification delivered successfully to %s", webhook_url)
                return True
            else:
                logger.warning(
                    "[WEBHOOK] Notification returned status %s: %s",
                    resp.status_code,
                    resp.text[:100],
                )
                return False
    except Exception as exc:
        logger.warning("[WEBHOOK] Failed to dispatch webhook notification: %s", exc)
        return False


def send_fill_notification_sync(
    webhook_url: str,
    result: FillResult,
    candidate: CandidateData,
    notes: str = "",
    timeout_seconds: float = 3.0,
) -> bool:
    """Synchronous version of send_fill_notification for sync batch runners."""
    if not webhook_url or not webhook_url.strip().startswith(("http://", "https://")):
        return False

    payload = build_webhook_payload(result, candidate, notes=notes)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(webhook_url, json=payload)
            return bool(resp.is_success or resp.status_code in (200, 201, 204))
    except Exception as exc:
        logger.warning("[WEBHOOK] Sync webhook error: %s", exc)
        return False
