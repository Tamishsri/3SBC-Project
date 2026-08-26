"""Concurrency, multi-user, and stress tests for heavy data flow."""

import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.file_lock import FileLock
from src.tracker import append_to_tracker, load_tracker
from src.models import CandidateData, PersonalInfo, FillResult
from src.worker_pool import ConcurrentWorkerPool, TaskItem


def test_file_lock_concurrent_thread_writes():
    """Verify that multiple concurrent threads writing to a file don't corrupt it."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "concurrent_test.txt"

        def worker_write(thread_id: int):
            for i in range(10):
                with FileLock(test_file):
                    with test_file.open("a", encoding="utf-8") as f:
                        f.write(f"thread_{thread_id}_line_{i}\n")

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker_write, tid) for tid in range(8)]
            for fut in futures:
                fut.result()

        lines = test_file.read_text(encoding="utf-8").strip().splitlines()
        # 8 threads * 10 lines = 80 lines exactly
        assert len(lines) == 80


def test_tracker_concurrent_process_writes():
    """Verify concurrent appends to application_log.csv from multiple simulated users."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "app_log.csv"

        candidate = CandidateData(
            personal=PersonalInfo(
                first_name="User",
                last_name="Test",
                email="user@example.com",
            )
        )
        fill_res = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/company/jobs/1",
            filled_fields=["First Name"],
        )

        def append_worker(user_id: int):
            for j in range(5):
                append_to_tracker(
                    fill_res,
                    candidate,
                    notes=f"User {user_id}",
                    log_path=csv_path,
                )

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(append_worker, uid) for uid in range(6)]
            for fut in futures:
                fut.result()

        entries = load_tracker(log_path=csv_path)
        assert len(entries) == 30  # 6 workers * 5 appends = 30 entries


@pytest.mark.asyncio
async def test_worker_pool_dispatches_concurrently():
    """Test ConcurrentWorkerPool orchestrates multiple tasks with isolated tabs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)

        tasks = []
        for i in range(4):
            fpath = dir_path / f"cand_{i}.json"
            fpath.write_text(
                '{"personal": {"first_name": "Name' + str(i) + '", "last_name": "Last", "email": "test' + str(i) + '@example.com"}}',
                encoding="utf-8",
            )
            tasks.append(TaskItem(task_id=f"task_{i}", data_file=fpath, user_id=f"user_{i}"))

        mock_result = FillResult(
            ats_platform="Lever",
            page_url="https://jobs.lever.co/company/job",
            filled_fields=["Full Name", "Email"],
            failed_fields=[],
            skipped_fields=[],
        )

        with patch("src.worker_pool.BrowserSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_page = AsyncMock()
            mock_session.create_isolated_page.return_value = mock_page
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            with patch("src.worker_pool.get_filler") as mock_get_filler:
                mock_filler = AsyncMock()
                mock_filler.fill.return_value = mock_result
                mock_get_filler.return_value = mock_filler

                pool = ConcurrentWorkerPool(max_concurrency=2, port=9222)
                outcomes = await pool.run_tasks(tasks)

                assert len(outcomes) == 4
                assert all(o.success for o in outcomes)
                assert outcomes[0].user_id == "user_0"
                assert outcomes[3].user_id == "user_3"
