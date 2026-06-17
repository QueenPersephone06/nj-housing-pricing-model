"""Unit tests for pricing analytics."""
import numpy as np
import pandas as pd

from src.pricing.pricing_analytics import _bed_bucket, _heat_index


def test_bed_buckets():
    assert _bed_bucket(0) == "1BR"
    assert _bed_bucket(1) == "1BR"
    assert _bed_bucket(2) == "2BR"
    assert _bed_bucket(3) == "3BR"
    assert _bed_bucket(4) == "4BR"
    assert _bed_bucket(5) == "5+BR"
    assert _bed_bucket(8) == "5+BR"
    assert _bed_bucket(np.nan) == "unk"


def test_heat_index_normalization():
    medians = pd.Series([100_000, 300_000, 500_000, 1_000_000], index=list("abcd"))
    hi = _heat_index(medians)
    assert hi.min() == 0
    assert hi.max() == 100
    assert hi.is_monotonic_increasing
