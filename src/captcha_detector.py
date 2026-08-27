"""Live CAPTCHA & Bot Challenge Detector for ATS Form Filler.

Monitors browser pages for Cloudflare Turnstile, Google reCAPTCHA,
hCaptcha, and Arkose Labs challenges. Provides non-crashing human
intervention pauses that resume automatically once solved.
"""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from playwright.async_api import Page
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


CAPTCHA_SIGNATURES: dict[str, list[str]] = {
    "Cloudflare Turnstile": [
        "iframe[src*='challenges.cloudflare.com']",
        "div.cf-turnstile",
        "#turnstile-wrapper",
        "[name='cf-turnstile-response']",
    ],
    "Google reCAPTCHA": [
        "iframe[src*='recaptcha']",
        "iframe[src*='google.com/recaptcha']",
        "div.g-recaptcha",
        ".grecaptcha-badge",
        "#g-recaptcha-response",
    ],
    "hCaptcha": [
        "iframe[src*='hcaptcha.com']",
        "div.h-captcha",
        "[name='h-captcha-response']",
    ],
    "Arkose Labs FunCaptcha": [
        "iframe[src*='arkoselabs']",
        "#fc-iframe-wrap",
        "div#captcha[data-e2e*='arkose']",
    ],
}


async def detect_captcha(page: Page) -> str | None:
    """Scan active page DOM and title for bot challenges or CAPTCHAs.

    Args:
        page: Playwright Page instance.

    Returns:
        Name of detected challenge provider, or None if clear.
    """
    try:
        # 1. Check title and text indicators
        title = (await page.title()).lower()
        if any(w in title for w in ["attention required", "just a moment...", "security check", "verify you are human"]):
            return "Cloudflare / Bot Challenge Page"

        # 2. Check selector signatures
        for provider, selectors in CAPTCHA_SIGNATURES.items():
            for sel in selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        loc = page.locator(sel).first
                        # Ensure element is not completely detached/hidden
                        if await loc.is_visible():
                            return provider
                except Exception:
                    continue

    except Exception as exc:
        logger.debug("[CAPTCHA] Detection check error: %s", exc)

    return None


async def handle_captcha_challenge(
    page: Page,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 1.5,
) -> bool:
    """Detect and pause for human resolution of bot challenges.

    If a CAPTCHA is detected, halts with a warning and polls until the
    user completes the challenge in their browser window.

    Args:
        page: Playwright Page instance.
        timeout_seconds: Maximum seconds to wait for user to solve (default: 120s).
        poll_interval_seconds: Seconds between check loops.

    Returns:
        True if no challenge exists or challenge was solved; False if timed out.
    """
    detected = await detect_captcha(page)
    if not detected:
        return True

    logger.warning("[CAPTCHA] Bot challenge detected on page: %s", detected)
    console.print()
    console.print(Panel(
        f"[bold yellow]⚠️  BOT CHALLENGE DETECTED: {detected}[/]\n\n"
        "• A CAPTCHA or verification screen is active in your browser window.\n"
        "• [bold cyan]Please solve the challenge directly in the browser.[/]\n"
        "• The script is waiting and will resume automatically once solved.",
        title="[bold red]Action Required[/]",
        border_style="yellow",
    ))

    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
        await asyncio.sleep(poll_interval_seconds)
        still_present = await detect_captcha(page)
        if not still_present:
            console.print("[bold green]✅ CAPTCHA challenge solved! Resuming automated fill...[/]\n")
            logger.info("[CAPTCHA] Challenge successfully solved by human.")
            return True

    console.print(f"[bold red]❌ Timed out after {timeout_seconds:.0f}s waiting for CAPTCHA resolution.[/]")
    return False
