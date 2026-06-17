"""Phase 5 — Pricing Analytics.

For each micro-market level (county / municipality / zip_cluster) computes:
    - n_listings  (with `low_sample` flag if < 10)
    - median_price
    - p10, p90 (price range)
    - median_price_per_sqft
    - median_price_by_bed (1, 2, 3, 4, 5+)
    - median_price_by_type
    - price_heat_index (normalized 0–100)

Also produces the FINAL Pricing Matrix CSV (Phase 10 deliverable):
    rows   = micro-market (county_municipality_zipcluster)
    cols   = (beds × property_type)
    values = median listing price
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.io import project_path, read_any
from src.utils.logger import get_logger

log = get_logger(__name__)


def _bed_bucket(b: float) -> str:
    if pd.isna(b):
        return "unk"
    b = int(round(b))
    if b <= 1:
        return "1BR"
    if b == 2:
        return "2BR"
    if b == 3:
        return "3BR"
    if b == 4:
        return "4BR"
    return "5+BR"


def _summary(group: pd.DataFrame, p_lo: int, p_hi: int) -> pd.Series:
    out = {
        "n_listings": len(group),
        "median_price": group["listing_price"].median(),
        f"p{p_lo}_price": group["listing_price"].quantile(p_lo / 100),
        f"p{p_hi}_price": group["listing_price"].quantile(p_hi / 100),
        "median_price_per_sqft": group["price_per_sqft"].median(),
    }
    # By bed bucket
    for bb, sub in group.groupby(group["bedrooms"].apply(_bed_bucket)):
        out[f"median_price_{bb}"] = sub["listing_price"].median()
    # By property type
    for pt, sub in group.groupby("property_type"):
        out[f"median_price_{pt.replace('/', '_')}"] = sub["listing_price"].median()
    return pd.Series(out)


def _heat_index(median_series: pd.Series) -> pd.Series:
    nj_median = median_series.median()
    raw = (median_series / nj_median) * 100.0
    # Normalize to 0–100 across markets (min-max)
    lo, hi = raw.min(), raw.max()
    if hi == lo:
        return pd.Series([50.0] * len(raw), index=raw.index)
    return (raw - lo) / (hi - lo) * 100.0


def compute_pricing_analytics(segmented_path: str | Path, cfg: dict[str, Any]) -> dict[str, Path]:
    df = read_any(segmented_path)
    p_lo = cfg["pricing"]["percentile_low"]
    p_hi = cfg["pricing"]["percentile_high"]
    min_n = cfg["pricing"]["min_listings_to_publish"]
    processed_dir = project_path(cfg["paths"]["processed_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}

    for level_name, keys in [
        ("county", ["county"]),
        ("municipality", ["county", "municipality"]),
        ("zip_cluster", ["county", "municipality", "zip_cluster"]),
    ]:
        # Build per-group summary rows manually (more robust than groupby.apply
        # which can lose columns when groups have heterogeneous bed/proptype mix)
        records: list[dict[str, Any]] = []
        for key, sub in df.groupby(keys, dropna=False):
            rec = {k: v for k, v in zip(keys, key if isinstance(key, tuple) else (key,))}
            rec.update(_summary(sub, p_lo, p_hi).to_dict())
            records.append(rec)
        rows = pd.DataFrame.from_records(records)
        rows["low_sample"] = rows["n_listings"] < min_n
        rows["price_heat_index"] = _heat_index(rows["median_price"])
        rows = rows.sort_values("median_price", ascending=False)

        out_path = processed_dir / f"pricing_by_{level_name}.csv"
        rows.to_csv(out_path, index=False)
        outputs[level_name] = out_path
        log.info("[%s] wrote %d rows → %s", level_name, len(rows), out_path)

    # ------- Pricing matrix (Phase 10 deliverable) ------------------------
    log.info("building final pricing matrix")
    df = df.copy()
    df["bed_bucket"] = df["bedrooms"].apply(_bed_bucket)
    df["micro_market"] = df["county"] + " / " + df["municipality"].fillna("Unknown") + " / " + df["zip_cluster"].astype(str)
    pivot = df.pivot_table(
        index="micro_market",
        columns=["property_type", "bed_bucket"],
        values="listing_price",
        aggfunc="median",
    ).round(-2)
    # Flatten the multi-index columns
    pivot.columns = [f"{pt}|{bb}" for pt, bb in pivot.columns.to_flat_index()]
    matrix_path = project_path(cfg["paths"]["outputs_dir"], "pricing_matrix.csv")
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    pivot.to_csv(matrix_path)
    outputs["pricing_matrix"] = matrix_path
    log.info("wrote pricing matrix (%d markets × %d cells) → %s", *pivot.shape, matrix_path)
    return outputs
