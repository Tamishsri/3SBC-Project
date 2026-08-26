"""ATS platform-specific form fillers.

Supported platforms:
- Greenhouse (boards.greenhouse.io) — with iframe support
- Lever (jobs.lever.co)
- Workday (*.myworkdayjobs.com)
- SmartRecruiters (careers.smartrecruiters.com)
"""

from src.fillers.greenhouse import GreenhouseFiller
from src.fillers.lever import LeverFiller
from src.fillers.workday import WorkdayFiller
from src.fillers.smartrecruiters import SmartRecruitersFiller

__all__ = [
    "GreenhouseFiller",
    "LeverFiller",
    "WorkdayFiller",
    "SmartRecruitersFiller",
]
