"""Unit tests for the Interactive Field Prompter & Learning Engine."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.interactive_prompter import prompt_user_for_field, persist_learned_answer
from src.models import CandidateData, PersonalInfo


@pytest.fixture
def sample_candidate() -> CandidateData:
    return CandidateData(
        personal=PersonalInfo(
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
        ),
        skills=["Python"],
        custom_answers={"existing_key": "existing_value"},
    )


def test_prompt_user_for_field_custom_input():
    """Verify input_func provides mock user response."""
    result = prompt_user_for_field(
        label="What is your desired salary?",
        field_type="text",
        default_value="$120k",
        input_func=lambda prompt: "$150k",
    )
    assert result == "$150k"


def test_prompt_user_for_field_empty_input_uses_default():
    """Verify empty user response falls back to default_value."""
    result = prompt_user_for_field(
        label="Notice period in days",
        field_type="text",
        default_value="30",
        input_func=lambda prompt: "",
    )
    assert result == "30"


def test_persist_learned_answer_in_memory(sample_candidate: CandidateData):
    """Verify learned answer is added to candidate.custom_answers."""
    success = persist_learned_answer(
        candidate=sample_candidate,
        label="Preferred Work Location",
        answer="Hybrid - Bangalore",
        save_to_disk=False,
    )
    assert success is True
    assert "preferred work location" in sample_candidate.custom_answers
    assert sample_candidate.custom_answers["preferred work location"] == "Hybrid - Bangalore"


def test_persist_learned_answer_to_disk(tmp_path: Path, sample_candidate: CandidateData):
    """Verify learned answer writes back to candidate JSON file on disk."""
    cand_file = tmp_path / "candidate_test.json"
    cand_file.write_text(sample_candidate.model_dump_json(indent=2), encoding="utf-8")

    success = persist_learned_answer(
        candidate=sample_candidate,
        label="Years of Experience",
        answer="6 years",
        candidate_file=cand_file,
        save_to_disk=True,
    )
    assert success is True

    disk_data = json.loads(cand_file.read_text(encoding="utf-8"))
    assert disk_data["custom_answers"]["years of experience"] == "6 years"
