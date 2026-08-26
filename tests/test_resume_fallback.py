"""Unit tests for the built-in local resume PDF and text fallback parser."""

import tempfile
from pathlib import Path
import pytest

from src.resume_fallback import (
    extract_text_from_file,
    parse_resume_text,
    parse_resume_file,
    parse_and_save_candidate,
)
from src.contract_verifier import verify_parser_payload


SAMPLE_RESUME_TEXT = """
Tamish Sridatta
Software Engineer
tamish.sridatta@example.com | +91-9876543210 | Chennai, Tamil Nadu, India
LinkedIn: https://linkedin.com/in/tamishsri
GitHub: https://github.com/Tamishsri
Portfolio: https://tamishsri.dev

TECHNICAL SKILLS:
Python, Playwright, FastAPI, Docker, Kubernetes, PostgreSQL, AWS, React, TypeScript, Git

WORK EXPERIENCE:
Senior Software Engineer - 3SBC Technologies (2022 - Present)
- Developed high-performance browser automation systems using Playwright and Python.
- Built distributed asynchronous backend microservices with FastAPI and PostgreSQL.

Software Engineer - Cloud Systems (2020 - 2022)
- Implemented containerized deployment pipelines in Docker and AWS.

EDUCATION:
B.Tech in Information Technology - Anna University (2016 - 2020)
"""


def test_parse_resume_text_extraction():
    """Verify name, email, phone, links, skills, and experience extraction."""
    cand = parse_resume_text(SAMPLE_RESUME_TEXT)

    assert cand.personal.first_name == "Tamish"
    assert cand.personal.last_name == "Sridatta"
    assert cand.personal.email == "tamish.sridatta@example.com"
    assert cand.personal.phone == "+919876543210"
    assert cand.personal.linkedin_url == "https://linkedin.com/in/tamishsri"
    assert cand.personal.github_url == "https://github.com/Tamishsri"
    assert "tamishsri.dev" in (cand.personal.website or "")

    # Skills dictionary matching
    assert "Python" in cand.skills
    assert "Playwright" in cand.skills
    assert "FastAPI" in cand.skills
    assert "Docker" in cand.skills
    assert "AWS" in cand.skills

    # Experience & Education
    assert len(cand.experience) >= 1
    assert len(cand.education) >= 1


def test_parsed_resume_passes_contract_verifier():
    """Verify that output from local fallback parser is 100% compliant with Saran's verifier."""
    cand = parse_resume_text(SAMPLE_RESUME_TEXT)
    payload = cand.model_dump()
    diagnostic = verify_parser_payload(payload)

    assert diagnostic.is_valid is True
    assert diagnostic.compatibility_score == 100.0


def test_parse_and_save_candidate_file():
    with tempfile.TemporaryDirectory() as tmp:
        txt_path = Path(tmp) / "resume.txt"
        txt_path.write_text(SAMPLE_RESUME_TEXT, encoding="utf-8")

        json_out = parse_and_save_candidate(txt_path)
        assert json_out.exists()
        assert json_out.suffix == ".json"

        cand = parse_resume_file(txt_path)
        assert cand.personal.full_name == "Tamish Sridatta"


def test_extract_text_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_text_from_file("non_existent_resume_file.pdf")
