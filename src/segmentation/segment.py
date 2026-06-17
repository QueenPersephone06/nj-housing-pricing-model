"""Phase 4 — Micro-Market Segmentation.

Level 1: County (all 21)
Level 2: Municipality
Level 3: ZIP cluster — ZIPs with <30 listings are grouped per (county,
         property_type) into a synthetic "{county}_smallzips" cluster
Level 4: Commuter Corridor (NYC / Philadelphia / Other)

Adds columns:
    zip_cluster   — string, either the original ZIP or a fallback cluster name
    corridor      — "NYC Corridor" | "Philadelphia Corridor" | "Other"
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.io import project_path, read_any, write_dataframe
from src.utils.logger import get_logger

log = get_logger(__name__)


def _assign_corridor(county: str, cfg: dict[str, Any]) -> str:
    if county in cfg["segmentation"]["corridor_nyc_counties"]:
        return "NYC Corridor"
    if county in cfg["segmentation"]["corridor_philly_counties"]:
        return "Philadelphia Corridor"
    return "Other"


def _build_zip_clusters(df: pd.DataFrame, min_size: int) -> pd.Series:
    counts = df.groupby("zip_code").size()
    small_zips = set(counts[counts < min_size].index)

    def _bucket(row: pd.Series) -> str:
        z = row["zip_code"]
        if z in small_zips:
            return f"{row['county']}_smallzips"
        return z

    return df.apply(_bucket, axis=1)


def segment(geocoded_path: str | Path, cfg: dict[str, Any]) -> Path:
    df = read_any(geocoded_path)

    df["zip_cluster"] = _build_zip_clusters(df, cfg["segmentation"]["zip_cluster_min_size"])
    df["corridor"] = df["county"].apply(lambda c: _assign_corridor(c, cfg))

    log.info("ZIP clusters: %d unique (incl. small-zip fallbacks)", df["zip_cluster"].nunique())
    log.info("corridor breakdown:\n%s", df["corridor"].value_counts().to_string())

    out_stem = project_path(cfg["paths"]["processed_dir"], "nj_housing_segmented")
    written = write_dataframe(df, out_stem, csv=False, parquet=True)
    log.info("segmented: %d rows → %s", len(df), written["parquet"])
    return written["parquet"]
