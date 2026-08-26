"""ATS platform router.

Detects which ATS platform the current page belongs to and returns
the appropriate form filler instance.
"""

from __future__ import annotations

import logging

from playwright.async_api import Page

from src.exceptions import UnsupportedATSError
from src.fillers.base import ATSFormFiller
from src.fillers.greenhouse import GreenhouseFiller
from src.fillers.lever import LeverFiller
from src.fillers.workday import WorkdayFiller
from src.models import CandidateData

logger = logging.getLogger(__name__)

# Registry of all available ATS fillers, checked in order
_FILLER_CLASSES: list[type[ATSFormFiller]] = [
    GreenhouseFiller,
    LeverFiller,
    WorkdayFiller,
]


async def get_filler(page: Page, candidate: CandidateData) -> ATSFormFiller:
    """Detect the ATS platform and return the appropriate filler.
    
    Iterates through registered fillers and returns the first one
    whose detect() method returns True.
    
    Args:
        page: The Playwright page with the ATS application form.
        candidate: Validated candidate data to fill into the form.
        
    Returns:
        An ATSFormFiller instance ready to fill the form.
        
    Raises:
        UnsupportedATSError: If no filler matches the current page.
    """
    url = page.url
    logger.info("Detecting ATS platform for: %s", url)

    for filler_cls in _FILLER_CLASSES:
        filler = filler_cls(page=page, candidate=candidate)
        if await filler.detect():
            logger.info("✅ Detected ATS platform: %s", filler.platform_name)
            return filler
        logger.debug("   ❌ Not %s", filler_cls.platform_name)

    supported = [cls.platform_name for cls in _FILLER_CLASSES]
    raise UnsupportedATSError(url=url, supported=supported)


def register_filler(filler_cls: type[ATSFormFiller]) -> None:
    """Register a new ATS filler class.
    
    Use this to add support for additional ATS platforms
    without modifying this module.
    
    Args:
        filler_cls: ATSFormFiller subclass to register.
    """
    if filler_cls not in _FILLER_CLASSES:
        _FILLER_CLASSES.append(filler_cls)
        logger.info("Registered new ATS filler: %s", filler_cls.platform_name)
