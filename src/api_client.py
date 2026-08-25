"""API client for fetching parsed candidate data from the backend.

Connects to the FastAPI backend service to retrieve resume data
that has been parsed by Saran's resume parser module.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from src.config import Config
from src.exceptions import APIConnectionError, DataValidationError
from src.models import CandidateData

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.5  # seconds: 1.5, 2.25, 3.375
REQUEST_TIMEOUT = 10.0  # seconds


async def fetch_candidate_data(
    candidate_id: str | int,
    config: Config,
) -> CandidateData:
    """Fetch and validate candidate data from the backend API.
    
    Makes an authenticated GET request to retrieve parsed resume data,
    then validates it against the CandidateData Pydantic model.
    
    Args:
        candidate_id: Unique identifier for the candidate.
        config: Application configuration with API URL and token.
        
    Returns:
        Validated CandidateData instance.
        
    Raises:
        DataValidationError: If required candidate fields are missing.
        APIConnectionError: If the API request fails after retries.
    """
    url = f"{config.api_base_url.rstrip('/')}/api/candidates/{candidate_id}/parsed-data"
    headers = {
        "Authorization": f"Bearer {config.api_token}",
        "Accept": "application/json",
    }

    logger.info("Fetching candidate data from: %s", url)

    # Retry loop with exponential backoff
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(url, headers=headers)

            if response.status_code == 401:
                raise APIConnectionError(
                    url=url,
                    status_code=401,
                    detail="Authentication failed. Check your API_TOKEN.",
                )

            if response.status_code == 404:
                raise APIConnectionError(
                    url=url,
                    status_code=404,
                    detail=f"Candidate {candidate_id} not found.",
                )

            if response.status_code != 200:
                raise APIConnectionError(
                    url=url,
                    status_code=response.status_code,
                    detail=response.text[:200],
                )

            # Parse and validate the response data
            raw_data: dict[str, Any] = response.json()
            logger.info("Received candidate data, validating...")

            return _validate_candidate_data(raw_data)

        except (APIConnectionError, DataValidationError):
            raise  # Don't retry validation or auth errors

        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning(
                "API request timed out (attempt %d/%d): %s",
                attempt, MAX_RETRIES, exc,
            )

        except httpx.ConnectError as exc:
            last_error = exc
            logger.warning(
                "API connection failed (attempt %d/%d): %s",
                attempt, MAX_RETRIES, exc,
            )

        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning(
                "HTTP error (attempt %d/%d): %s",
                attempt, MAX_RETRIES, exc,
            )

        # Exponential backoff before retry
        if attempt < MAX_RETRIES:
            import asyncio
            wait_time = RETRY_BACKOFF_FACTOR * (attempt ** 2)
            logger.info("Retrying in %.1f seconds...", wait_time)
            await asyncio.sleep(wait_time)

    # All retries exhausted
    raise APIConnectionError(
        url=url,
        detail=f"All {MAX_RETRIES} retry attempts failed. Last error: {last_error}",
    )


def _validate_candidate_data(raw_data: dict[str, Any]) -> CandidateData:
    """Validate raw JSON data against the CandidateData schema.
    
    Raises:
        DataValidationError: If validation fails with specific field details.
    """
    try:
        candidate = CandidateData.model_validate(raw_data)
        logger.info(
            "✅ Candidate data validated: %s (%s)",
            candidate.personal.full_name,
            candidate.personal.email,
        )
        return candidate

    except ValidationError as exc:
        missing_fields: list[str] = []
        details: list[str] = []

        for error in exc.errors():
            field_path = " → ".join(str(loc) for loc in error["loc"])
            error_type = error["type"]
            msg = error["msg"]

            if error_type == "missing":
                missing_fields.append(field_path)
            else:
                details.append(f"{field_path}: {msg}")

        raise DataValidationError(
            missing_fields=missing_fields,
            detail="; ".join(details) if details else "",
        ) from exc


def load_candidate_from_file(file_path: str) -> CandidateData:
    """Load and validate candidate data from a local JSON file.
    
    Useful for testing or when working offline without the backend API.
    
    Args:
        file_path: Path to a JSON file containing candidate data.
        
    Returns:
        Validated CandidateData instance.
        
    Raises:
        DataValidationError: If the data is invalid.
        FileNotFoundError: If the file doesn't exist.
    """
    import json
    from pathlib import Path

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Candidate data file not found: {file_path}")

    logger.info("Loading candidate data from file: %s", file_path)
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    return _validate_candidate_data(raw_data)
