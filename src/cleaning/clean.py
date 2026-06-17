"""Phase 2 — Data Cleaning.

Steps
-----
1. Remove duplicates (address+zip hash)
2. Remove price outliers (< $10k or > $20M)
3. Standardize property types into 5 canonical buckets
4. Impute bed/bath/sqft via median + create *_was_missing indicator columns
5. Validate ZIP codes (5-digit, NJ range 07xxx–08xxx)
6. Validate county assignments against the canonical 21-county list
7. Emit data-quality report markdown

Output
------
- data/interim/nj_housing_clean.parquet
- reports/data_quality_report.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.io import project_path, read_any, write_dataframe
from src.utils.logger import get_logger

log = get_logger(__name__)

# --------------- Property-type taxonomy -----------------------------------
PROP_TYPE_MAP: dict[str, str] = {
    # Single Family
    "single family": "Single Family",
    "single_family": "Single Family",
    "single-family home": "Single Family",
    "single family residential": "Single Family",
    "house": "Single Family",
    "detached": "Single Family",
    "sfr": "Single Family",
    # Condo / Co-op
    "condo": "Condo/Co-op",
    "condominium": "Condo/Co-op",
    "co-op": "Condo/Co-op",
    "coop": "Condo/Co-op",
    "cooperative": "Condo/Co-op",
    "condo/co-op": "Condo/Co-op",
    "apartment": "Condo/Co-op",
    # Townhouse
    "townhouse": "Townhouse",
    "townhome": "Townhouse",
    "row home": "Townhouse",
    "rowhouse": "Townhouse",
    # Multi-Family
    "multi family": "Multi-Family",
    "multi-family": "Multi-Family",
    "multifamily": "Multi-Family",
    "duplex": "Multi-Family",
    "triplex": "Multi-Family",
    "fourplex": "Multi-Family",
    "2-4 units": "Multi-Family",
    # Land
    "land": "Land",
    "lot": "Land",
    "vacant land": "Land",
    "lots/land": "Land",
}

NJ_COUNTIES = {
    "Atlantic", "Bergen", "Burlington", "Camden", "Cape May", "Cumberland",
    "Essex", "Gloucester", "Hudson", "Hunterdon", "Mercer", "Middlesex",
    "Monmouth", "Morris", "Ocean", "Passaic", "Salem", "Somerset", "Sussex",
    "Union", "Warren",
}


def _standardize_property_type(s: str | None) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "Single Family"  # default if missing
    key = str(s).strip().lower()
    return PROP_TYPE_MAP.get(key, "Single Family")


def _valid_nj_zip(z: Any) -> bool:
    if z is None or pd.isna(z):
        return False
    s = str(z).strip()
    if not s.isdigit() or len(s) != 5:
        return False
    return s[:2] in ("07", "08")


def clean_data(raw_path: str | Path, cfg: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    df = read_any(raw_path)
    log.info("loaded raw: %d rows × %d cols", *df.shape)
    metrics: dict[str, Any] = {"input_rows": len(df)}

    # ---- 1. Duplicates (already deduped by scraper, but defensive) -------
    before = len(df)
    df = df.drop_duplicates(subset=["full_address", "zip_code"], keep="first")
    metrics["duplicates_removed"] = before - len(df)

    # ---- 2. Outliers ------------------------------------------------------
    lo, hi = cfg["cleaning"]["min_price"], cfg["cleaning"]["max_price"]
    pre = len(df)
    outliers_mask = (df["listing_price"] < lo) | (df["listing_price"] > hi)
    df = df.loc[~outliers_mask].copy()
    metrics["price_outliers_removed"] = pre - len(df)

    # ---- 3. Standardize property types -----------------------------------
    df["property_type"] = df["property_type"].apply(_standardize_property_type)

    # ---- 4. Missing-value handling ---------------------------------------
    missing_cols = ["bedrooms", "bathrooms", "sqft"]
    for col in missing_cols:
        df[f"{col}_was_missing"] = df[col].isna().astype(int)

    # median impute by (county, property_type) where possible, else global
    for col in missing_cols:
        med = df.groupby(["county", "property_type"])[col].transform("median")
        df[col] = df[col].fillna(med)
        df[col] = df[col].fillna(df[col].median())

    # ---- 5. ZIP validation -----------------------------------------------
    df["zip_code"] = df["zip_code"].astype(str).str.zfill(5)
    bad_zip = ~df["zip_code"].apply(_valid_nj_zip)
    metrics["invalid_zips_dropped"] = int(bad_zip.sum())
    df = df.loc[~bad_zip].copy()

    # ---- 6. County validation --------------------------------------------
    bad_county = ~df["county"].isin(NJ_COUNTIES)
    metrics["invalid_counties_dropped"] = int(bad_county.sum())
    df = df.loc[~bad_county].copy()

    # ---- Recompute price_per_sqft ----------------------------------------
    df["price_per_sqft"] = df["listing_price"] / df["sqft"].replace(0, np.nan)

    metrics["output_rows"] = len(df)
    metrics["completeness_pct"] = float((1 - df.isna().mean().mean()) * 100)

    # ---- Write outputs ----------------------------------------------------
    out_stem = project_path(cfg["paths"]["interim_dir"], "nj_housing_clean")
    written = write_dataframe(df, out_stem, csv=False, parquet=True)
    log.info("cleaned: %d rows → %s", len(df), written["parquet"])

    # ---- Data-quality report (markdown) ----------------------------------
    qa_md = _data_quality_report(df, metrics)
    qa_path = project_path(cfg["paths"]["reports_dir"], "data_quality_report.md")
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(qa_md, encoding="utf-8")
    log.info("wrote data-quality report: %s", qa_path)

    return written["parquet"], metrics


def _data_quality_report(df: pd.DataFrame, metrics: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Data Quality Report\n")
    lines.append(f"_Generated automatically by `src/cleaning/clean.py`._\n")
    lines.append("## Pipeline metrics\n")
    for k, v in metrics.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("\n## Per-column completeness\n")
    miss = df.isna().mean().sort_values(ascending=False) * 100
    lines.append("| column | missing % | unique values |")
    lines.append("|---|---:|---:|")
    for col in df.columns:
        lines.append(f"| `{col}` | {miss[col]:.2f}% | {df[col].nunique(dropna=True):,} |")

    lines.append("\n## County coverage\n")
    by_county = df.groupby("county").size().sort_values(ascending=False)
    lines.append("| county | n listings |")
    lines.append("|---|---:|")
    for c, n in by_county.items():
        lines.append(f"| {c} | {n:,} |")
    if len(by_county) != 21:
        lines.append(f"\n⚠️ **Warning:** {len(by_county)} of 21 NJ counties present.")
    else:
        lines.append("\n✅ All 21 NJ counties covered.")

    lines.append("\n## Property-type distribution\n")
    pt = df["property_type"].value_counts(dropna=False)
    lines.append("| type | n |")
    lines.append("|---|---:|")
    for t, n in pt.items():
        lines.append(f"| {t} | {n:,} |")

    return "\n".join(lines)
