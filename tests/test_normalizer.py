"""Unit tests for the data normalizer module."""

import pytest
from src.normalizer import (
    sanitize_text,
    normalize_phone,
    parse_location,
    decompose_full_name,
)


class TestSanitizeText:
    def test_smart_quotes_replaced(self):
        raw = "‘Smart quotes’ and “double quotes” with – dash and — emdash"
        clean = sanitize_text(raw)
        assert clean == "'Smart quotes' and \"double quotes\" with - dash and - emdash"

    def test_non_breaking_spaces_collapsed(self):
        raw = "Word1\xa0Word2    Word3"
        clean = sanitize_text(raw)
        assert clean == "Word1 Word2 Word3"

    def test_none_handled(self):
        assert sanitize_text(None) is None


class TestNormalizePhone:
    def test_us_standard_with_plus1(self):
        p = normalize_phone("+1 (415) 555-0199")
        assert p is not None
        assert p.country_code == "+1"
        assert p.national_number == "4155550199"
        assert p.formatted_e164 == "+14155550199"

    def test_india_standard_with_plus91(self):
        p = normalize_phone("+91-9876543210")
        assert p is not None
        assert p.country_code == "+91"
        assert p.national_number == "9876543210"
        assert p.formatted_e164 == "+919876543210"

    def test_germany_standard_with_plus49(self):
        p = normalize_phone("+49 30 901820")
        assert p is not None
        assert p.country_code == "+49"
        assert p.formatted_e164 == "+4930901820"

    def test_10_digits_without_country_code(self):
        p = normalize_phone("9876543210")
        assert p is not None
        assert p.national_number == "9876543210"

    def test_invalid_phone_returns_none(self):
        assert normalize_phone("") is None
        assert normalize_phone("123") is None
        assert normalize_phone(None) is None


class TestParseLocation:
    def test_three_part_location(self):
        loc = parse_location("Chennai, Tamil Nadu, India")
        assert loc.city == "Chennai"
        assert loc.state_province == "Tamil Nadu"
        assert loc.country == "India"

    def test_two_part_city_state(self):
        loc = parse_location("San Francisco, CA")
        assert loc.city == "San Francisco"
        assert loc.state_province == "CA"

    def test_two_part_city_country(self):
        loc = parse_location("London, UK")
        assert loc.city == "London"
        assert loc.country == "UK"

    def test_single_part_or_remote(self):
        loc = parse_location("Remote")
        assert loc.city == "Remote"
        assert loc.state_province == ""

    def test_empty_location(self):
        loc = parse_location(None)
        assert loc.city == ""
        assert loc.country == ""


class TestDecomposeFullName:
    def test_standard_two_names(self):
        first, last = decompose_full_name("Tamish Sridatta")
        assert first == "Tamish"
        assert last == "Sridatta"

    def test_three_names(self):
        first, last = decompose_full_name("John Fitzgerald Kennedy")
        assert first == "John"
        assert last == "Fitzgerald Kennedy"

    def test_honorific_stripped(self):
        first, last = decompose_full_name("Dr. Jane Doe")
        assert first == "Jane"
        assert last == "Doe"

    def test_suffix_stripped(self):
        first, last = decompose_full_name("Robert Smith, Jr.")
        assert first == "Robert"
        assert last == "Smith"

    def test_single_name(self):
        first, last = decompose_full_name("Cher")
        assert first == "Cher"
        assert last == "Cher"
