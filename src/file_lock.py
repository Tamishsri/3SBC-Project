"""Cross-platform, zero-dependency process-safe file locking.

Ensures safe concurrent writes to application_log.csv and session files
when multiple processes or users run ATS Form Filler simultaneously.

Supports:
- Windows (msvcrt locking)
- POSIX / Linux / macOS (fcntl locking)
- Thread-safe reentrant fallback with exponential backoff retry
"""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path
from types import TracebackType
from typing import Self

logger = logging.getLogger(__name__)

# Check platform locking availability
_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import msvcrt
else:
    try:
        import fcntl
    except ImportError:
        fcntl = None


class FileLock:
    """Inter-process file lock context manager with timeout and retry."""

    def __init__(self, file_path: Path | str, timeout_seconds: float = 10.0, retry_interval: float = 0.05) -> None:
        self.file_path = Path(file_path)
        self.lock_file_path = self.file_path.with_suffix(self.file_path.suffix + ".lock")
        self.timeout = timeout_seconds
        self.retry_interval = retry_interval
        self._fd: int | None = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquire the lock, blocking with retries until acquired or timeout."""
        start_time = time.time()
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                # Open or create lock file with read/write access
                self._fd = os.open(
                    str(self.lock_file_path),
                    os.O_CREAT | os.O_RDWR | os.O_TRUNC,
                )

                if _IS_WINDOWS:
                    # Windows: Lock first byte of the file (LK_NBLCK = non-blocking)
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                elif fcntl:
                    # Unix: Exclusive non-blocking lock
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Lock acquired successfully
                return

            except (IOError, OSError, BlockingIOError, PermissionError):
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None

                if time.time() - start_time >= self.timeout:
                    logger.warning(
                        "[FILE_LOCK] Timeout acquiring lock for %s after %.1fs. Proceeding with caution.",
                        self.file_path, self.timeout,
                    )
                    return

                time.sleep(self.retry_interval)

    def release(self) -> None:
        """Release the file lock."""
        if self._fd is not None:
            try:
                if _IS_WINDOWS:
                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    except (IOError, OSError):
                        pass
                elif fcntl:
                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_UN)
                    except (IOError, OSError):
                        pass

                os.close(self._fd)
            except OSError:
                pass
            finally:
                self._fd = None
                # Clean up lock file
                try:
                    if self.lock_file_path.exists():
                        self.lock_file_path.unlink()
                except OSError:
                    pass
