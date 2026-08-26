"""Unit tests for the preference presets manager."""

import tempfile
from pathlib import Path
import pytest

from src.models import CandidateData, PersonalInfo, WorkAuthorization, Demographics
from src.presets import (
    save_preset,
    load_preset,
    list_presets,
    merge_candidate_with_preset,
)


@pytest.fixture
def sample_candidate():
    return CandidateData(
        personal=PersonalInfo(
            first_name="Tamish",
            last_name="Sridatta",
            email="tamish@example.com",
        ),
        work_authorization=WorkAuthorization(
            expected_salary="$180,000",  # Explicit candidate field
        ),
        custom_answers={
            "willing to travel": "No",  # Explicit candidate answer
        },
    )


def test_save_and_load_preset():
    with tempfile.TemporaryDirectory() as tmp:
        preset_dir = Path(tmp)

        data = {
            "work_authorization": {
                "authorized_to_work": True,
                "requires_sponsorship": False,
                "notice_period_days": 15,
                "expected_salary": "$150,000",
            },
            "demographics": {
                "gender": "Male",
                "race_ethnicity": "Asian",
            },
            "custom_answers": {
                "willing to travel": "Yes, 50%",
                "preferred_editor": "VS Code",
            },
            "cover_letter_template": "Preset Cover Letter",
        }

        path = save_preset("default_us", data, presets_dir=preset_dir)
        assert path.exists()
        assert path.name == "default_us.json"

        loaded = load_preset("default_us", presets_dir=preset_dir)
        assert loaded["preset_name"] == "default_us"
        assert loaded["work_authorization"]["notice_period_days"] == 15
        assert loaded["demographics"]["gender"] == "Male"


def test_list_presets():
    with tempfile.TemporaryDirectory() as tmp:
        preset_dir = Path(tmp)
        save_preset("alpha", {}, presets_dir=preset_dir)
        save_preset("beta", {}, presets_dir=preset_dir)

        presets = list_presets(presets_dir=preset_dir)
        assert presets == ["alpha", "beta"]


def test_load_non_existent_preset_raises():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            load_preset("does_not_exist", presets_dir=Path(tmp))


def test_merge_candidate_with_preset_non_destructive(sample_candidate):
    with tempfile.TemporaryDirectory() as tmp:
        preset_dir = Path(tmp)

        preset_data = {
            "work_authorization": {
                "authorized_to_work": True,
                "requires_sponsorship": False,
                "notice_period_days": 30,
                "expected_salary": "$120,000",  # Lower than candidate's $180,000
            },
            "demographics": {
                "gender": "Male",
                "race_ethnicity": "Asian",
            },
            "custom_answers": {
                "willing to travel": "Yes, 100%",  # Candidate has "No"
                "remote_preference": "Hybrid",
            },
            "cover_letter_template": "Default preset cover letter.",
        }
        save_preset("my_preset", preset_data, presets_dir=preset_dir)

        merged = merge_candidate_with_preset(sample_candidate, "my_preset", presets_dir=preset_dir)

        # 1. Candidate's explicit expected salary MUST NOT be overwritten
        assert merged.work_authorization.expected_salary == "$180,000"
        # 2. Preset's notice period SHOULD be populated
        assert merged.work_authorization.notice_period_days == 30

        # 3. Candidate's explicit custom answer MUST NOT be overwritten
        assert merged.custom_answers["willing to travel"] == "No"
        # 4. Preset's additional custom answer SHOULD be added
        assert merged.custom_answers["remote_preference"] == "Hybrid"

        # 5. Empty cover letter SHOULD receive preset template
        assert merged.cover_letter == "Default preset cover letter."
