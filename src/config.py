"""Configuration management for the ATS Form Filler.

Loads settings from environment variables and .env files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:8000")
    )
    api_token: str = field(
        default_factory=lambda: os.getenv("API_TOKEN", "")
    )
    browser_debug_port: int = field(
        default_factory=lambda: int(os.getenv("BROWSER_DEBUG_PORT", "9222"))
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    def validate(self) -> None:
        """Validate that all required configuration is present."""
        if not self.api_base_url:
            raise ValueError("API_BASE_URL is not configured")
        if not self.api_token:
            raise ValueError(
                "API_TOKEN is not configured. Set it in your .env file."
            )


def get_config() -> Config:
    """Create and return the application configuration."""
    return Config()
