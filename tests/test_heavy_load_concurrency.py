"""Extreme heavy load, high-volume concurrency, and error boundary stress tests."""

import asyncio
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from src.file_lock import FileLock
from src.models import CandidateData, FillResult, PersonalInfo
from src.tracker import append_to_tracker, load_tracker
from src.worker_pool import ConcurrentWorkerPool, TaskItem


def test_extreme_file_lock_high_contention():
    """50 simultaneous worker threads competing for a single FileLock across 500 total writes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = Path(tmp_dir) / "high_contention.txt"

        def write_burst(thread_idx: int):
            for i in range(10):
                with FileLock(target_file, timeout_seconds=15.0, retry_interval=0.01):
                    with target_file.open("a", encoding="utf-8") as f:
                        f.write(f"T{thread_idx:02d}_L{i:03d}\n")

        # 50 concurrent threads
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(write_burst, tid) for tid in range(50)]
            for fut in futures:
                fut.result()

        lines = target_file.read_text(encoding="utf-8").strip().splitlines()
        # Exactly 50 threads * 10 writes = 500 lines
        assert len(lines) == 500
        # Verify no lines were interleaved/corrupted
        for line in lines:
            assert line.startswith("T") and "_L" in line


def test_heavy_tracker_burst_writes():
    """Simulate 30 concurrent users logging 300 job applications simultaneously."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_file = Path(tmp_dir) / "stress_tracker.csv"

        cand = CandidateData(
            personal=PersonalInfo(first_name="Burst", last_name="User", email="burst@example.com")
        )
        fill_res = FillResult(
            ats_platform="Greenhouse",
            page_url="https://boards.greenhouse.io/company/job",
            filled_fields=["First Name", "Email"],
        )

        def user_burst(user_idx: int):
            for j in range(10):
                append_to_tracker(
                    fill_res,
                    cand,
                    notes=f"Stress User {user_idx} batch {j}",
                    log_path=csv_file,
                )

        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(user_burst, uid) for uid in range(30)]
            for fut in futures:
                fut.result()

        entries = load_tracker(log_path=csv_file)
        assert len(entries) == 300


@pytest.mark.asyncio
async def test_worker_pool_100_task_burst_with_error_boundaries():
    """Burst test: 100 tasks (50 valid + 50 corrupt payloads) executed with concurrency limit.

    Verifies:
    1. 100% of valid tasks succeed.
    2. 100% of corrupt tasks are safely caught and reported without crashing the pool.
    3. Concurrency semaphore smoothly processes all 100 items without memory starvation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        tasks = []

        # Create 50 valid candidate files
        for i in range(50):
            p = dir_path / f"valid_{i:03d}.json"
            p.write_text(
                json.dumps({
                    "personal": {
                        "first_name": f"ValidUser{i}",
                        "last_name": "Test",
                        "email": f"valid{i}@example.com"
                    },
                    "skills": ["Python", "FastAPI"]
                }),
                encoding="utf-8",
            )
            tasks.append(TaskItem(task_id=f"val_{i:03d}", data_file=p, user_id=f"user_{i % 10}"))

        # Create 50 corrupted files (broken JSON, missing required fields, empty files)
        for i in range(50):
            p = dir_path / f"corrupt_{i:03d}.json"
            if i % 3 == 0:
                p.write_text("{broken_json: true,", encoding="utf-8")
            elif i % 3 == 1:
                p.write_text(json.dumps({"personal": {"phone": "123"}}), encoding="utf-8")  # missing first_name, email
            else:
                p.write_text("", encoding="utf-8")  # empty file

            tasks.append(TaskItem(task_id=f"bad_{i:03d}", data_file=p, user_id=f"user_{i % 10}"))

        mock_fill_result = FillResult(
            ats_platform="Lever",
            page_url="https://jobs.lever.co/company/job",
            filled_fields=["Full Name", "Email"],
        )

        with patch("src.worker_pool.BrowserSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_page = AsyncMock()
            mock_session.create_isolated_page.return_value = mock_page
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            with patch("src.worker_pool.get_filler") as mock_get_filler:
                mock_filler = AsyncMock()
                mock_filler.fill.return_value = mock_fill_result
                mock_get_filler.return_value = mock_filler

                # Run pool with 5 concurrent workers
                pool = ConcurrentWorkerPool(max_concurrency=5, port=9222)
                outcomes = await pool.run_tasks(tasks)

                assert len(outcomes) == 100
                succeeded = sum(1 for o in outcomes if o.success)
                failed = sum(1 for o in outcomes if not o.success)

                assert succeeded == 50
                assert failed == 50

                # Verify all corrupted tasks have error messages
                corrupt_outcomes = [o for o in outcomes if o.task_id.startswith("bad_")]
                for co in corrupt_outcomes:
                    assert co.success is False
                    assert co.error is not None
                    assert len(co.error) > 0
