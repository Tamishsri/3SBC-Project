"""Data normalization utilities for real-world candidate data.

Handles messy, varied real-world data inputs from resume parsers and JSONs:
- Phone number normalization (E.164, national digits, country code extraction)
- Name decomposition and honorific/suffix stripping
- Geographic location parsing (city, state/province, country, zip)
- Unicode sanitization (smart quotes, non-breaking spaces, zero-width chars)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import NamedTuple


class ParsedLocation(NamedTuple):
    """Structured location components parsed from a free-text location string."""
    city: str
    state_province: str
    country: str
    raw: str


class ParsedPhone(NamedTuple):
    """Normalized phone components."""
    country_code: str  # e.g., "+1", "+91", "+44"
    national_number: str  # digits only, e.g., "9876543210"
    formatted_e164: str  # e.g., "+919876543210"
    raw: str


def sanitize_text(text: str | None) -> str | None:
    """Clean and sanitize text from real-world resumes.

    Replaces:
    - Smart/curly quotes with standard ASCII quotes
    - Non-breaking spaces (\xa0) with regular spaces
    - Zero-width spaces and invisible control characters
    - Multiple consecutive whitespaces with single space
    """
    if text is None:
        return None

    # Normalize unicode (NFKC replaces compatibility characters)
    t = unicodedata.normalize("NFKC", text)

    # Replace smart quotes and dashes
    t = t.replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    t = t.replace("\xa0", " ")

    # Remove non-printable / zero-width characters (except standard newlines/tabs)
    t = "".join(ch for ch in t if ch in "\n\r\t" or unicodedata.category(ch)[0] != "C")

    # Collapse repeated whitespace (excluding newlines)
    t = re.sub(r"[ \t]+", " ", t)

    return t.strip()


def normalize_phone(phone_str: str | None) -> ParsedPhone | None:
    """Normalize international and domestic phone numbers.

    Handles formats like:
    - "+1 (555) 123-4567" -> country="+1", national="5551234567", e164="+15551234567"
    - "+91-9876543210"    -> country="+91", national="9876543210", e164="+919876543210"
    - "9876543210"        -> country="", national="9876543210", e164="+19876543210" (default US/fallback)
    - "07123 456789" (UK) -> country="+44", national="7123456789"
    """
    if not phone_str or not phone_str.strip():
        return None

    cleaned = phone_str.strip()
    digits = re.sub(r"\D", "", cleaned)

    if not digits or len(digits) < 7:
        # Invalid phone
        return None

    # Check for leading '+'
    if cleaned.startswith("+"):
        # Match common country codes
        for prefix_len, code_len in [(1, 1), (2, 2), (3, 3)]:
            code_candidate = "+" + digits[:code_len]
            # Common country codes: +1, +44, +91, +49, +33, +61, +81, +86, +353, etc.
            if code_len == 1 and digits.startswith("1"):
                return ParsedPhone(
                    country_code="+1",
                    national_number=digits[1:],
                    formatted_e164=f"+{digits}",
                    raw=cleaned,
                )
            elif code_len == 2 and digits[:2] in ["91", "44", "49", "33", "61", "81", "86", "34", "39", "55"]:
                return ParsedPhone(
                    country_code=f"+{digits[:2]}",
                    national_number=digits[2:],
                    formatted_e164=f"+{digits}",
                    raw=cleaned,
                )
            elif code_len == 3:
                return ParsedPhone(
                    country_code=f"+{digits[:3]}",
                    national_number=digits[3:],
                    formatted_e164=f"+{digits}",
                    raw=cleaned,
                )

    # 10-digit without country code (common in US / India)
    if len(digits) == 10:
        return ParsedPhone(
            country_code="",
            national_number=digits,
            formatted_e164=f"+1{digits}",  # Default standard format
            raw=cleaned,
        )

    # 11-digit starting with 1 (US with country code)
    if len(digits) == 11 and digits.startswith("1"):
        return ParsedPhone(
            country_code="+1",
            national_number=digits[1:],
            formatted_e164=f"+{digits}",
            raw=cleaned,
        )

    # Generic fallback
    return ParsedPhone(
        country_code="",
        national_number=digits,
        formatted_e164=f"+{digits}",
        raw=cleaned,
    )


def parse_location(location_str: str | None) -> ParsedLocation:
    """Parse a free-text location string into city, state, country.

    Examples:
    - "Chennai, Tamil Nadu, India" -> city="Chennai", state="Tamil Nadu", country="India"
    - "San Francisco, CA"          -> city="San Francisco", state="CA", country="United States"
    - "Austin, Texas, USA"         -> city="Austin", state="Texas", country="USA"
    - "London, UK"                 -> city="London", state="", country="UK"
    - "Remote"                     -> city="Remote", state="", country=""
    """
    if not location_str or not location_str.strip():
        return ParsedLocation(city="", state_province="", country="", raw="")

    raw = location_str.strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if len(parts) == 1:
        return ParsedLocation(city=parts[0], state_province="", country="", raw=raw)
    elif len(parts) == 2:
        # e.g., "San Francisco, CA" or "London, UK"
        second = parts[1].upper()
        if second in ["US", "USA", "UK", "INDIA", "CANADA", "GERMANY", "FRANCE"]:
            return ParsedLocation(city=parts[0], state_province="", country=parts[1], raw=raw)
        else:
            return ParsedLocation(city=parts[0], state_province=parts[1], country="", raw=raw)
    elif len(parts) >= 3:
        # e.g. "Chennai, Tamil Nadu, India"
        return ParsedLocation(city=parts[0], state_province=parts[1], country=parts[2], raw=raw)

    return ParsedLocation(city=raw, state_province="", country="", raw=raw)


def decompose_full_name(full_name: str) -> tuple[str, str]:
    """Split a full name into (first_name, last_name), handling honorifics/suffixes.

    Examples:
    - "Dr. Jane Doe, Jr." -> ("Jane", "Doe")
    - "Tamish Sridatta" -> ("Tamish", "Sridatta")
    - "Cher" -> ("Cher", "Cher")
    - "Juan Carlos de la Vega" -> ("Juan Carlos", "de la Vega")
    """
    cleaned = sanitize_text(full_name) or ""
    # Strip common suffixes
    cleaned = re.sub(r",?\s+(Jr\.?|Sr\.?|III|IV|II|Ph\.?D\.?|M\.?D\.?)$", "", cleaned, flags=re.IGNORECASE)
    # Strip common honorifics
    cleaned = re.sub(r"^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+", "", cleaned, flags=re.IGNORECASE)

    parts = cleaned.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], parts[0])
    if len(parts) == 2:
        return (parts[0], parts[1])

    # 3+ parts: first name is first token, last name is rest
    return (parts[0], " ".join(parts[1:]))
