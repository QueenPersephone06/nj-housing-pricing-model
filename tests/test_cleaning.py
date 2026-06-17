"""Unit tests for cleaning module."""
import pandas as pd
import pytest

from src.cleaning.clean import _standardize_property_type, _valid_nj_zip


@pytest.mark.parametrize("raw,expected", [
    ("single family", "Single Family"),
    ("Single Family Residential", "Single Family"),
    ("CONDO", "Condo/Co-op"),
    ("co-op", "Condo/Co-op"),
    ("Townhouse", "Townhouse"),
    ("Duplex", "Multi-Family"),
    ("Land", "Land"),
    ("Lot", "Land"),
    (None, "Single Family"),
    ("Unrecognized", "Single Family"),
])
def test_property_type_map(raw, expected):
    assert _standardize_property_type(raw) == expected


@pytest.mark.parametrize("z,ok", [
    ("07302", True),    # Jersey City
    ("08540", True),    # Princeton
    ("12345", False),   # NY
    ("0730", False),    # too short
    ("abcde", False),   # not digits
    (None, False),
])
def test_zip_validation(z, ok):
    assert _valid_nj_zip(z) is ok
