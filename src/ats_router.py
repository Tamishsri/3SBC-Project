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
from src.fillers.smartrecruiters import SmartRecruitersFiller
from src.fillers.generic import GenericAdaptiveFiller
from src.models import CandidateData

logger = logging.getLogger(__name__)

# Registry of specialized ATS fillers, checked in prioritized order
_FILLER_CLASSES: list[type[ATSFormFiller]] = [
    GreenhouseFiller,
    LeverFiller,
    WorkdayFiller,
    SmartRecruitersFiller,
]


async def get_filler(
    page: Page,
    candidate: CandidateData,
    *,
    human_mode: bool = False,
    multi_page: bool = False,
    allow_generic: bool = False,
    interactive: bool = False,
    candidate_file: str | Path | None = None,
) -> ATSFormFiller:
    """Detect the ATS platform from the page URL and return the matching filler.

    Iterates through all registered filler classes, calling their detect()
    method. Returns the first match.

    Args:
        page: Playwright Page object.
        candidate: CandidateData to fill into the form.
        human_mode: If True, type with human-like delays.
        multi_page: If True, auto-advance multi-step wizard applications.
        allow_generic: If True, fallback to GenericAdaptiveFiller for arbitrary web forms.
        interactive: If True, prompt user for unmapped questions and learn answers.
        candidate_file: Optional file path to persist learned answers to disk.

    Returns:
        An instance of the appropriate ATSFormFiller subclass.

    Raises:
        UnsupportedATSError: If no filler matches the current page.
    """
    url = page.url
    logger.info("Detecting ATS platform for: %s", url)

    for filler_cls in _FILLER_CLASSES:
        filler = filler_cls(
            page=page,
            candidate=candidate,
            human_mode=human_mode,
            multi_page=multi_page,
            interactive=interactive,
            candidate_file=candidate_file,
        )
        if await filler.detect():
            logger.info("[OK] Detected ATS platform: %s", filler.platform_name)
            return filler
        logger.debug("   Not %s", filler_cls.platform_name)

    if allow_generic:
        generic_filler = GenericAdaptiveFiller(
            page=page,
            candidate=candidate,
            human_mode=human_mode,
            multi_page=multi_page,
            interactive=interactive,
            candidate_file=candidate_file,
        )
        if await generic_filler.detect():
            logger.info("[OK] Using Adaptive Generic Web Form filler for: %s", url)
            return generic_filler

    supported = [cls.platform_name for cls in _FILLER_CLASSES]
    if allow_generic:
        supported.append(GenericAdaptiveFiller.platform_name)
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
