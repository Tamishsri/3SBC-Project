"""Custom exception hierarchy for the ATS Form Filler.

Every error is specific and loud — no silent failures.
Each exception carries a human-readable message explaining
exactly what went wrong and what the user should do.
"""

from __future__ import annotations


class ATSFillerError(Exception):
    """Base exception for all ATS Form Filler errors.
    
    All custom exceptions inherit from this so callers can
    catch the entire family with a single handler when needed.
    """


class BrowserConnectionError(ATSFillerError):
    """Failed to connect to the browser via Chrome DevTools Protocol.
    
    This typically means Chrome/Edge was not launched with the
    --remote-debugging-port flag, or the port number is wrong.
    """

    def __init__(self, port: int, original_error: Exception | None = None) -> None:
        self.port = port
        self.original_error = original_error
        message = (
            f"\n{'=' * 60}\n"
            f"  BROWSER CONNECTION FAILED (port {port})\n"
            f"{'=' * 60}\n"
            f"\n"
            f"  Could not connect to a browser debugging session.\n"
            f"\n"
            f"  To fix this, launch Chrome with debugging enabled:\n"
            f"\n"
            f"    1. Close ALL Chrome windows\n"
            f"    2. Run: launch_browser.bat\n"
            f"       OR manually run:\n"
            f'       chrome --remote-debugging-port={port}\n'
            f"    3. Re-run this script\n"
            f"\n"
        )
        if original_error:
            message += f"  Original error: {original_error}\n"
        message += f"{'=' * 60}"
        super().__init__(message)


class FieldNotFoundError(ATSFillerError):
    """A target form field could not be located in the DOM.
    
    This usually means the ATS platform updated its UI layout
    and the selectors need to be updated.
    """

    def __init__(self, field_name: str, ats_platform: str, selectors_tried: list[str] | None = None) -> None:
        self.field_name = field_name
        self.ats_platform = ats_platform
        self.selectors_tried = selectors_tried or []
        selectors_info = ""
        if self.selectors_tried:
            selectors_info = "\n    Selectors tried:\n" + "\n".join(
                f"      - {s}" for s in self.selectors_tried
            )
        message = (
            f"Failed to locate '{field_name}' field on {ats_platform} form. "
            f"The page layout may have changed."
            f"{selectors_info}"
        )
        super().__init__(message)


class DataValidationError(ATSFillerError):
    """Candidate data is missing required fields or has invalid values.
    
    This is caught BEFORE the browser session is launched,
    ensuring we never waste time on incomplete data.
    """

    def __init__(self, missing_fields: list[str] | None = None, detail: str = "") -> None:
        self.missing_fields = missing_fields or []
        parts = ["Candidate data validation failed."]
        if self.missing_fields:
            parts.append(f"Missing required fields: {', '.join(self.missing_fields)}")
        if detail:
            parts.append(detail)
        parts.append("Fix the data source and retry.")
        super().__init__(" ".join(parts))


class UnsupportedATSError(ATSFillerError):
    """The current page URL does not match any supported ATS platform."""

    def __init__(self, url: str, supported: list[str] | None = None) -> None:
        self.url = url
        self.supported = supported or ["Greenhouse (boards.greenhouse.io)", "Lever (jobs.lever.co)"]
        supported_list = "\n".join(f"  - {s}" for s in self.supported)
        message = (
            f"No form filler available for: {url}\n"
            f"\n"
            f"Supported ATS platforms:\n"
            f"{supported_list}\n"
            f"\n"
            f"Navigate to a supported ATS application page and retry."
        )
        super().__init__(message)


class ResumeUploadError(ATSFillerError):
    """Failed to upload the resume file to the ATS form."""

    def __init__(self, file_path: str, reason: str = "") -> None:
        self.file_path = file_path
        message = f"Failed to upload resume: {file_path}"
        if reason:
            message += f" — {reason}"
        super().__init__(message)


class APIConnectionError(ATSFillerError):
    """Failed to connect to or authenticate with the backend API."""

    def __init__(self, url: str, status_code: int | None = None, detail: str = "") -> None:
        self.url = url
        self.status_code = status_code
        parts = [f"API request failed: {url}"]
        if status_code:
            parts.append(f"(HTTP {status_code})")
        if detail:
            parts.append(f"— {detail}")
        super().__init__(" ".join(parts))
