"""Tests for the Pydantic data models."""

import pytest
from pydantic import ValidationError

from src.models import CandidateData, Education, FillResult, PersonalInfo, WorkExperience


class TestPersonalInfo:
    """Tests for PersonalInfo model."""

    def test_valid_personal_info(self):
        """Valid personal info should be accepted."""
        info = PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
            phone="+1-555-0100",
        )
        assert info.first_name == "Tamish"
        assert info.last_name == "Sridatta"
        assert info.full_name == "Tamish Sridatta"

    def test_missing_first_name_raises(self):
        """Missing first_name should raise ValidationError."""
        with pytest.raises(ValidationError):
            PersonalInfo(
                first_name="",
                last_name="Sridatta",
                email="tamish@example.com",
            )

    def test_invalid_email_raises(self):
        """Invalid email format should raise ValidationError."""
        with pytest.raises(ValidationError):
            PersonalInfo(
                first_name="Tamish",
                last_name="Sridatta",
                email="not-an-email",
            )

    def test_whitespace_stripping(self):
        """Names should have whitespace stripped."""
        info = PersonalInfo(
            first_name="  Tamish  ",
            last_name="  Sridatta  ",
            email="tamish@example.com",
        )
        assert info.first_name == "Tamish"
        assert info.last_name == "Sridatta"

    def test_optional_fields_default_none(self):
        """Optional fields should default to None."""
        info = PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        )
        assert info.phone is None
        assert info.linkedin_url is None
        assert info.location is None
        assert info.website is None


class TestCandidateData:
    """Tests for the top-level CandidateData model."""

    def test_minimal_valid_candidate(self):
        """Candidate with only required fields should be accepted."""
        data = CandidateData(
            personal=PersonalInfo(
                first_name="Tamish",
                last_name="Sridatta",
                email="tamish@example.com",
            )
        )
        assert data.personal.full_name == "Tamish Sridatta"
        assert data.experience == []
        assert data.education == []
        assert data.skills == []

    def test_full_candidate(self):
        """Full candidate data should be accepted."""
        data = CandidateData(
            personal=PersonalInfo(
                first_name="Tamish",
                last_name="Sridatta",
                email="tamish@example.com",
                phone="+1-555-0100",
                linkedin_url="https://linkedin.com/in/tamish",
            ),
            experience=[
                WorkExperience(
                    company="TechCorp",
                    title="Software Engineer",
                    start_date="2023-01",
                    description="Built things",
                )
            ],
            education=[
                Education(
                    institution="MIT",
                    degree="B.S. Computer Science",
                )
            ],
            skills=["Python", "Playwright", "FastAPI"],
            resume_file_path="C:/path/to/resume.pdf",
        )
        assert len(data.experience) == 1
        assert data.experience[0].is_current  # end_date is None
        assert len(data.skills) == 3

    def test_missing_personal_raises(self):
        """Missing personal field should raise ValidationError."""
        with pytest.raises(ValidationError):
            CandidateData()  # type: ignore

    def test_skills_deduplication(self):
        """Duplicate skills should be removed."""
        data = CandidateData(
            personal=PersonalInfo(
                first_name="Tamish",
                last_name="Sridatta",
                email="tamish@example.com",
            ),
            skills=["Python", "python", "PYTHON", "JavaScript"],
        )
        assert len(data.skills) == 2
        assert "Python" in data.skills
        assert "JavaScript" in data.skills

    def test_from_json(self):
        """Should parse from raw JSON dict (simulating API response)."""
        raw = {
            "personal": {
                "first_name": "Tamish",
                "last_name": "Sridatta",
                "email": "tamish@example.com",
            },
            "skills": ["Python"],
        }
        data = CandidateData.model_validate(raw)
        assert data.personal.first_name == "Tamish"


class TestFillResult:
    """Tests for the FillResult model."""

    def test_success_rate_all_filled(self):
        result = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/test",
            filled_fields=["First Name", "Last Name", "Email"],
        )
        assert result.success_rate == 100.0
        assert not result.has_failures

    def test_success_rate_with_failures(self):
        result = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/test",
            filled_fields=["First Name", "Email"],
            failed_fields=["Phone"],
        )
        assert result.success_rate == pytest.approx(66.67, abs=0.1)
        assert result.has_failures

    def test_success_rate_empty(self):
        result = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/test",
        )
        assert result.success_rate == 0.0


class TestWorkAuthAndDemographics:
    """Tests for WorkAuthorization and Demographics models."""

    def test_default_work_authorization(self):
        from src.models import WorkAuthorization
        auth = WorkAuthorization()
        assert auth.authorized_to_work is True
        assert auth.requires_sponsorship is False
        assert auth.notice_period_days is None
        assert auth.expected_salary is None
        assert auth.willing_to_relocate is True

    def test_custom_work_authorization(self):
        from src.models import WorkAuthorization
        auth = WorkAuthorization(
            authorized_to_work=False,
            requires_sponsorship=True,
            notice_period_days=30,
            expected_salary="$120k",
            willing_to_relocate=False,
        )
        assert auth.authorized_to_work is False
        assert auth.requires_sponsorship is True
        assert auth.notice_period_days == 30
        assert auth.expected_salary == "$120k"
        assert auth.willing_to_relocate is False

    def test_default_demographics(self):
        from src.models import Demographics
        demo = Demographics()
        assert "Decline" in demo.gender
        assert "Decline" in demo.race_ethnicity
        assert demo.veteran_status == "I am not a protected veteran"
        assert "not wish" in demo.disability_status.lower()

    def test_candidate_data_with_custom_answers(self):
        cand = CandidateData(
            personal=PersonalInfo(first_name="A", last_name="B", email="a@b.com"),
            custom_answers={"notice": "30 days", "salary": "$150k"},
        )
        assert cand.custom_answers["notice"] == "30 days"
        assert cand.custom_answers["salary"] == "$150k"
