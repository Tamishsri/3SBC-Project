"""Playwright CDP browser connection manager.

Connects to an existing Chrome/Edge session via the Chrome DevTools Protocol.
The user must launch their browser with --remote-debugging-port=XXXX for this to work.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.exceptions import BrowserConnectionError

logger = logging.getLogger(__name__)


class BrowserSession:
    """Manages a CDP connection to an existing browser session.
    
    Usage as async context manager:
        async with BrowserSession(port=9222) as session:
            page = await session.get_active_page()
            # ... use page ...
    """

    def __init__(self, port: int = 9222) -> None:
        self.port = port
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        """Connect to the browser debugging session."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clean up Playwright resources without closing the user's browser."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish a CDP connection to the browser.
        
        Raises:
            BrowserConnectionError: If connection fails.
        """
        endpoint = f"http://localhost:{self.port}"
        logger.info("Connecting to browser at %s ...", endpoint)

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
            logger.info(
                "Connected successfully. Browser has %d context(s).",
                len(self._browser.contexts),
            )
        except Exception as exc:
            await self.disconnect()
            raise BrowserConnectionError(port=self.port, original_error=exc) from exc

    async def disconnect(self) -> None:
        """Disconnect from the browser WITHOUT closing it.
        
        The user's browser session remains open and unaffected.
        """
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            self._browser = None
            logger.info("Disconnected from browser session.")

    async def get_active_page(self) -> Page:
        """Return the currently active (last) page/tab.
        
        Raises:
            BrowserConnectionError: If no browser is connected or no pages exist.
        """
        if not self._browser:
            raise BrowserConnectionError(
                port=self.port,
                original_error=RuntimeError("Not connected. Call connect() first."),
            )

        contexts = self._browser.contexts
        if not contexts:
            raise BrowserConnectionError(
                port=self.port,
                original_error=RuntimeError(
                    "No browser contexts found. Is a browser window open?"
                ),
            )

        # Use the first context (default profile)
        context = contexts[0]
        pages = context.pages
        if not pages:
            logger.info("No active tabs found. Creating a new tab...")
            page = await context.new_page()
            return page

        # Return the last (most recently active) page
        page = pages[-1]
        logger.info("Active page: %s", page.url)
        return page

    async def get_page_by_url(self, url_fragment: str) -> Page | None:
        """Find a page whose URL contains the given fragment.
        
        Args:
            url_fragment: Substring to search for in page URLs.
            
        Returns:
            The matching Page, or None if no match found.
        """
        if not self._browser:
            return None

        for context in self._browser.contexts:
            for page in context.pages:
                if url_fragment.lower() in page.url.lower():
                    logger.info("Found page matching '%s': %s", url_fragment, page.url)
                    return page

        logger.warning("No page found matching '%s'", url_fragment)
        return None

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected to a browser."""
        return self._browser is not None and self._browser.is_connected()
