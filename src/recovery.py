"""Batch Session Recovery & State Checkpoint Manager.

Persists progress checkpoints during large batch runs to `.ats_batch_recovery.json`.
Allows interrupted batch runs (browser crashes, sleep mode, network drops)
to be seamlessly resumed with `--resume-batch` without duplicate processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.file_lock import ProcessFileLock

logger = logging.getLogger(__name__)

_DEFAULT_RECOVERY_FILE = Path(".ats_batch_recovery.json")


def save_checkpoint(
    batch_dir: str | Path,
    completed_file: str | Path,
    success: bool = True,
    recovery_path: Path | None = None,
) -> None:
    """Atomically record a processed candidate file into the recovery checkpoint.

    Args:
        batch_dir: Base directory of the batch.
        completed_file: Filename or path of the candidate just processed.
        success: Whether the candidate fill succeeded.
        recovery_path: Optional custom recovery JSON path.
    """
    rec_path = recovery_path or _DEFAULT_RECOVERY_FILE
    file_stem = Path(completed_file).name
    lock_path = rec_path.with_suffix(".lock")

    with ProcessFileLock(lock_path):
        data: dict[str, Any] = {
            "batch_dir": str(Path(batch_dir).resolve()),
            "last_updated": datetime.now().isoformat(),
            "completed_files": [],
            "failed_files": [],
        }

        if rec_path.is_file():
            try:
                existing = json.loads(rec_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    data["batch_dir"] = existing.get("batch_dir", data["batch_dir"])
                    data["completed_files"] = existing.get("completed_files", [])
                    data["failed_files"] = existing.get("failed_files", [])
            except Exception as exc:
                logger.warning("[RECOVERY] Error reading checkpoint, initializing new: %s", exc)

        if success:
            if file_stem not in data["completed_files"]:
                data["completed_files"].append(file_stem)
        else:
            if file_stem not in data["failed_files"]:
                data["failed_files"].append(file_stem)

        rec_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("[RECOVERY] Checkpointed: %s (Success=%s)", file_stem, success)


def load_recovery_checkpoint(recovery_path: Path | None = None) -> dict[str, Any] | None:
    """Load existing recovery checkpoint data if present."""
    rec_path = recovery_path or _DEFAULT_RECOVERY_FILE
    if not rec_path.is_file():
        return None

    try:
        return json.loads(rec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[RECOVERY] Failed to parse recovery checkpoint: %s", exc)
        return None


def get_remaining_batch_files(
    batch_dir: str | Path,
    recovery_path: Path | None = None,
) -> list[Path]:
    """Return sorted list of JSON files in batch_dir that have NOT yet been completed.

    Args:
        batch_dir: Directory containing candidate JSONs.
        recovery_path: Optional custom recovery checkpoint path.

    Returns:
        Filtered list of Path objects for remaining candidates.
    """
    target_dir = Path(batch_dir)
    all_files = [f for f in sorted(target_dir.glob("*.json")) if not f.name.startswith(".")]

    checkpoint = load_recovery_checkpoint(recovery_path)
    if not checkpoint:
        return all_files

    completed_set = set(checkpoint.get("completed_files", []))
    remaining = [f for f in all_files if f.name not in completed_set]
    logger.info(
        "[RECOVERY] Resuming batch: %d total, %d already completed, %d remaining.",
        len(all_files),
        len(completed_set),
        len(remaining),
    )
    return remaining


def clear_checkpoint(recovery_path: Path | None = None) -> None:
    """Remove checkpoint file upon successful full batch completion."""
    rec_path = recovery_path or _DEFAULT_RECOVERY_FILE
    lock_path = rec_path.with_suffix(".lock")
    try:
        if rec_path.is_file():
            rec_path.unlink(missing_ok=True)
            logger.info("[RECOVERY] Checkpoint cleared upon batch completion.")
        if lock_path.is_file():
            lock_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("[RECOVERY] Error clearing checkpoint files: %s", exc)
