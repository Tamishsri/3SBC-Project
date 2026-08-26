"""Pydantic data models for the ATS Form Filler.

These models define the EXACT data contract between the resume parser
(built by teammate Saran) and this form filler module. Any changes to
these models must be coordinated with the parser team.

Schema version: 1.0.0
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class DegreeLevel(StrEnum):
    """Standard degree level classifications."""
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    CERTIFICATION = "certification"
    OTHER = "other"


class PersonalInfo(BaseModel):
    """Candidate's personal and contact information.
    
    Fields marked as required (no default) MUST be present for the
    form filler to proceed. Optional fields are filled when available.
    """

    first_name: Annotated[str, Field(min_length=1, description="Candidate's first/given name")]
    last_name: Annotated[str, Field(min_length=1, description="Candidate's last/family name")]
    email: EmailStr = Field(description="Primary contact email, validated format")
    phone: str | None = Field(default=None, description="Phone number in any format")
    linkedin_url: str | None = Field(default=None, description="Full LinkedIn profile URL")
    github_url: str | None = Field(default=None, description="Full GitHub profile URL")
    location: str | None = Field(default=None, description="City, State or full address")
    website: str | None = Field(default=None, description="Personal website or portfolio URL")

    @property
    def full_name(self) -> str:
        """Return the candidate's full name."""
        return f"{self.first_name} {self.last_name}"

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip leading/trailing whitespace from names."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        """Strip whitespace from phone numbers."""
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class WorkExperience(BaseModel):
    """A single work experience entry."""

    company: str = Field(min_length=1, description="Employer/company name")
    title: str = Field(min_length=1, description="Job title")
    start_date: str | None = Field(default=None, description="Start date (flexible format)")
    end_date: str | None = Field(
        default=None,
        description="End date (flexible format). None indicates 'Present'/current role"
    )
    description: str | None = Field(
        default=None,
        description="Role description, responsibilities, achievements"
    )
    location: str | None = Field(default=None, description="Job location")

    @property
    def is_current(self) -> bool:
        """Return True if this is the candidate's current role."""
        return self.end_date is None


class Education(BaseModel):
    """A single education entry."""

    institution: str = Field(min_length=1, description="School/university name")
    degree: str = Field(min_length=1, description="Degree name (e.g., 'B.S. Computer Science')")
    field_of_study: str | None = Field(default=None, description="Major/concentration")
    degree_level: DegreeLevel | None = Field(default=None, description="Standardized degree level")
    graduation_date: str | None = Field(default=None, description="Graduation date (flexible format)")
    gpa: str | None = Field(default=None, description="GPA if listed on resume")


class CandidateData(BaseModel):
    """Top-level model containing all parsed resume data.
    
    This is the primary data structure passed to ATSFormFiller.
    The `personal` field is required; others default to empty lists.
    
    Example JSON:
    ```json
    {
        "personal": {
            "first_name": "Tamish",
            "last_name": "Sridatta",
            "email": "tamish@example.com",
            "phone": "+1-555-0100"
        },
        "experience": [...],
        "education": [...],
        "skills": ["Python", "Playwright"],
        "resume_file_path": "C:/path/to/resume.pdf"
    }
    ```
    """

    personal: PersonalInfo = Field(description="Required personal/contact information")
    experience: list[WorkExperience] = Field(
        default_factory=list,
        description="Work experience entries, ordered most recent first"
    )
    education: list[Education] = Field(
        default_factory=list,
        description="Education entries, ordered most recent first"
    )
    skills: list[str] = Field(
        default_factory=list,
        description="List of skills/technologies"
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="Professional certifications"
    )
    cover_letter: str | None = Field(
        default=None,
        description="Optional cover letter text. If not provided, fillers auto-generate one."
    )
    resume_file_path: str | None = Field(
        default=None,
        description="Absolute local path to resume PDF/DOCX for upload"
    )

    @field_validator("skills", "certifications", mode="before")
    @classmethod
    def deduplicate_lists(cls, v: list[str]) -> list[str]:
        """Remove duplicates while preserving order."""
        if isinstance(v, list):
            seen = set()
            result = []
            for item in v:
                item_lower = item.lower().strip()
                if item_lower not in seen:
                    seen.add(item_lower)
                    result.append(item.strip())
            return result
        return v

    @model_validator(mode="after")
    def warn_empty_sections(self) -> CandidateData:
        """Log warnings for empty sections (but don't fail)."""
        import logging
        logger = logging.getLogger(__name__)
        if not self.experience:
            logger.warning("Candidate data has no work experience entries")
        if not self.education:
            logger.warning("Candidate data has no education entries")
        return self


class FillResult(BaseModel):
    """Result of a form filling operation.
    
    Returned by ATSFormFiller.fill() to report what happened.
    """

    ats_platform: str = Field(description="Name of the ATS platform (e.g., 'Greenhouse')")
    page_url: str = Field(description="URL of the form that was filled")
    filled_fields: list[str] = Field(
        default_factory=list,
        description="Fields that were successfully filled"
    )
    failed_fields: list[str] = Field(
        default_factory=list,
        description="Fields that could not be located or filled"
    )
    skipped_fields: list[str] = Field(
        default_factory=list,
        description="Fields skipped because candidate data was not available"
    )

    @property
    def success_rate(self) -> float:
        """Percentage of attempted fields that were successfully filled."""
        total = len(self.filled_fields) + len(self.failed_fields)
        if total == 0:
            return 0.0
        return len(self.filled_fields) / total * 100

    @property
    def has_failures(self) -> bool:
        """Return True if any fields failed to fill."""
        return len(self.failed_fields) > 0
