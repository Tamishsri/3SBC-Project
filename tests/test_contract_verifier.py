"""Unit tests for the resume parser contract verifier module (for teammate Saran)."""

import json
import tempfile
from pathlib import Path
import pytest

from src.contract_verifier import (
    verify_parser_payload,
    verify_parser_file,
    ContractDiagnostic,
)


def test_valid_payload_passes_100_percent():
    payload = {
        "personal": {
            "first_name": "Saran",
            "last_name": "Engineer",
            "email": "saran@example.com",
            "phone": "+91-9876543210",
        },
        "experience": [
            {"company": "AI Labs", "title": "ML Engineer"}
        ],
        "education": [
            {"institution": "Anna University", "degree": "B.E."}
        ],
        "skills": ["Python", "FastAPI", "NLP"],
    }
    diag = verify_parser_payload(payload)
    assert diag.is_valid is True
    assert diag.compatibility_score == 100.0
    assert diag.candidate_name == "Saran Engineer"
    assert len(diag.missing_required) == 0


def test_alias_detection_and_suggestions():
    """Verify that common aliases (fname, work_exp, tech_skills) are detected and suggested."""
    payload = {
        "personal": {
            "fname": "Saran",  # Alias for first_name
            "last_name": "Test",
            "email": "test@example.com",
        },
        "work_exp": [  # Alias for experience
            {"company": "Tech", "title": "Dev"}
        ],
        "tech_skills": ["Python"],  # Alias for skills
    }
    diag = verify_parser_payload(payload)
    # first_name was missing because fname was used
    assert diag.is_valid is False
    assert any("first_name" in m for m in diag.missing_required)

    # Check alias suggestions
    suggested_found = [found for found, _ in diag.alias_suggestions]
    assert "work_exp" in suggested_found
    assert "tech_skills" in suggested_found
    assert "personal.fname" in suggested_found


def test_missing_personal_object():
    """When personal info is completely missing."""
    payload = {
        "skills": ["Python"],
    }
    diag = verify_parser_payload(payload)
    assert diag.is_valid is False
    assert diag.compatibility_score < 50.0
    assert any("personal" in m for m in diag.missing_required)


def test_verify_parser_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json.dumps({
            "personal": {
                "first_name": "Tamish",
                "last_name": "Sridatta",
                "email": "tamish@example.com",
            }
        }))
        temp_path = f.name

    try:
        diag = verify_parser_file(temp_path)
        assert diag.is_valid is True
        assert diag.candidate_name == "Tamish Sridatta"
    finally:
        Path(temp_path).unlink(missing_ok=True)
