"""Unit tests for the batch processor."""

import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.batch import run_batch, process_single_candidate, BatchResult
from src.models import FillResult, CandidateData, PersonalInfo


@pytest.mark.asyncio
async def test_batch_runner_processes_directory():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)

        # Create 2 valid candidates
        for i in [1, 2]:
            file_path = dir_path / f"cand_{i}.json"
            data = {
                "personal": {
                    "first_name": f"User{i}",
                    "last_name": f"Test{i}",
                    "email": f"user{i}@example.com",
                },
                "skills": ["Python"],
            }
            file_path.write_text(json.dumps(data), encoding="utf-8")

        # Mock BrowserSession and get_filler so it doesn't need a real browser
        mock_result = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/test/job/1",
            filled_fields=["First Name", "Last Name", "Email"],
            failed_fields=[],
            skipped_fields=[],
        )

        with patch("src.batch.BrowserSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_page = AsyncMock()
            mock_session.get_active_page.return_value = mock_page
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            with patch("src.batch.get_filler") as mock_get_filler:
                mock_filler = AsyncMock()
                mock_filler.fill.return_value = mock_result
                mock_get_filler.return_value = mock_filler

                results = await run_batch(
                    batch_dir=dir_path,
                    port=9222,
                    delay_seconds=0.0,
                )

                assert len(results) == 2
                assert all(r.success for r in results)
                assert results[0].candidate_name == "User1 Test1"
                assert results[1].candidate_name == "User2 Test2"
