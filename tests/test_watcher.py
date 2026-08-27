"""Unit tests for the Drop-Folder Inbox Watcher Daemon."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from src.models import CandidateData, PersonalInfo, FillResult
from src.watcher import process_inbox_file, run_inbox_watcher


@pytest.fixture
def sample_candidate_json(tmp_path: Path) -> Path:
    cand = CandidateData(
        personal=PersonalInfo(
            first_name="Alice",
            last_name="Smith",
            email="alice.smith@example.com",
            phone="+14155552671",
        ),
        skills=["Python", "FastAPI"],
    )
    file_path = tmp_path / "candidate_alice.json"
    file_path.write_text(cand.model_dump_json(indent=2), encoding="utf-8")
    return file_path


@pytest.mark.asyncio
async def test_process_inbox_file_skips_unsupported(tmp_path: Path):
    """Verify non-resume files (.exe, .zip) are safely ignored."""
    bad_file = tmp_path / "archive.zip"
    bad_file.write_text("dummy", encoding="utf-8")
    res = await process_inbox_file(bad_file, move_to_processed=False)
    assert res is None


@pytest.mark.asyncio
async def test_process_inbox_file_mocked_execution(sample_candidate_json: Path, tmp_path: Path):
    """Verify candidate file is parsed, filled, and moved to processed directory."""
    processed_dir = tmp_path / "processed"

    mock_result = FillResult(
        ats_platform="Greenhouse",
        page_url="https://boards.greenhouse.io/test/jobs/1",
        filled_fields=["First Name", "Email"],
    )

    mock_filler = AsyncMock()
    mock_filler.fill.return_value = mock_result

    with patch("src.watcher.BrowserSession") as mock_session_cls, \
         patch("src.watcher.get_filler", return_value=mock_filler), \
         patch("src.watcher.handle_captcha_challenge", return_value=True), \
         patch("src.watcher.save_report"), \
         patch("src.watcher.append_to_tracker"):

        mock_session = AsyncMock()
        mock_page = AsyncMock()
        mock_session.connect.return_value = mock_page
        mock_session_cls.return_value = mock_session

        res = await process_inbox_file(
            sample_candidate_json,
            port=9222,
            move_to_processed=True,
            processed_dir=processed_dir,
        )

        assert res is not None
        assert res.ats_platform == "Greenhouse"
        assert (processed_dir / sample_candidate_json.name).exists()


@pytest.mark.asyncio
async def test_run_inbox_watcher_terminates_on_max_events(tmp_path: Path):
    """Verify watcher cleanly terminates when max_events threshold is reached."""
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()

    # Drop a simple candidate file
    test_cand = inbox_dir / "test_cand.json"
    test_cand.write_text(json.dumps({
        "personal": {
            "first_name": "Test",
            "last_name": "User",
            "email": "test.user@example.com",
        },
        "skills": ["Go"]
    }), encoding="utf-8")

    processed_events = []
    def on_processed(p, r):
        processed_events.append(p)

    with patch("src.watcher.process_inbox_file", return_value=FillResult(ats_platform="Lever", page_url="http://test")):
        await run_inbox_watcher(
            watch_dir=inbox_dir,
            poll_interval=0.1,
            max_events=1,
            on_event_processed=on_processed,
        )

    assert len(processed_events) == 1
