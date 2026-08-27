"""Unit tests for the batch session recovery and state checkpointer."""

import tempfile
from pathlib import Path

from src.recovery import (
    save_checkpoint,
    load_recovery_checkpoint,
    get_remaining_batch_files,
    clear_checkpoint,
)


def test_save_and_load_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        rec_file = tmp_dir / ".test_recovery.json"

        save_checkpoint(batch_dir=tmp_dir, completed_file="cand_01.json", success=True, recovery_path=rec_file)
        save_checkpoint(batch_dir=tmp_dir, completed_file="cand_02.json", success=True, recovery_path=rec_file)
        save_checkpoint(batch_dir=tmp_dir, completed_file="cand_03.json", success=False, recovery_path=rec_file)

        cp = load_recovery_checkpoint(recovery_path=rec_file)
        assert cp is not None
        assert "cand_01.json" in cp["completed_files"]
        assert "cand_02.json" in cp["completed_files"]
        assert "cand_03.json" in cp["failed_files"]


def test_get_remaining_batch_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        rec_file = tmp_dir / ".test_recovery.json"

        # Create dummy batch files
        f1 = tmp_dir / "01.json"
        f2 = tmp_dir / "02.json"
        f3 = tmp_dir / "03.json"
        for f in [f1, f2, f3]:
            f.write_text("{}", encoding="utf-8")

        # Checkpoint f1 as completed
        save_checkpoint(batch_dir=tmp_dir, completed_file="01.json", success=True, recovery_path=rec_file)

        remaining = get_remaining_batch_files(batch_dir=tmp_dir, recovery_path=rec_file)
        remaining_names = [f.name for f in remaining]

        assert "01.json" not in remaining_names
        assert "02.json" in remaining_names
        assert "03.json" in remaining_names


def test_clear_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        rec_file = tmp_dir / ".test_recovery.json"

        save_checkpoint(batch_dir=tmp_dir, completed_file="01.json", success=True, recovery_path=rec_file)
        assert rec_file.exists()

        clear_checkpoint(recovery_path=rec_file)
        assert not rec_file.exists()
