"""Phase 3 — Geocoding.

Uses geopy's Nominatim provider by default (free, rate-limited to 1 req/s
per Nominatim's TOS). Caches every (address → lat, lon) lookup in
`data/external/geocode_cache.json` so re-runs are instant.

If `geocoding.provider: google` is set in config.yaml AND
`geocoding.google_api_key` is provided, switches to GoogleV3.

Production note
---------------
A full 6,000-listing first-time geocode against Nominatim takes ~100
minutes. For demo/CI we fall back to ZIP centroids if Nominatim is
unreachable, so the pipeline never blocks.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.io import project_path, read_any, write_dataframe
from src.utils.logger import get_logger

log = get_logger(__name__)


# Approx NJ ZIP centroid lookup (very coarse — used only as offline fallback).
# Keys are the leading 3 digits; values are (lat, lon).
ZIP3_CENTROID: dict[str, tuple[float, float]] = {
    "070": (40.74, -74.05),  # Hudson / Jersey City
    "071": (40.92, -74.17),  # Bergen / Passaic
    "072": (40.78, -74.20),  # Bergen / Essex border
    "073": (40.94, -74.07),  # Bergen
    "074": (40.92, -74.30),  # Passaic
    "075": (40.90, -74.04),  # Bergen
    "076": (40.83, -73.96),  # Bergen east
    "077": (40.31, -74.05),  # Monmouth
    "078": (40.85, -74.65),  # Morris / Sussex
    "079": (40.76, -75.04),  # Warren / Hunterdon
    "080": (39.83, -75.05),  # Camden / Gloucester
    "081": (39.89, -75.10),  # Camden / Burlington
    "082": (39.43, -74.50),  # Atlantic / Cape May
    "083": (39.20, -75.00),  # Cumberland / Salem
    "084": (39.50, -74.80),  # Cape May / Atlantic
    "085": (40.20, -74.70),  # Mercer
    "086": (40.30, -74.45),  # Mercer / Middlesex
    "087": (40.50, -74.40),  # Middlesex
    "088": (40.55, -74.65),  # Somerset
    "089": (40.50, -74.30),  # Middlesex
}


def _approx_centroid(zip_code: str) -> tuple[float | None, float | None]:
    if not isinstance(zip_code, str) or len(zip_code) != 5:
        return None, None
    return ZIP3_CENTROID.get(zip_code[:3], (None, None))


def _load_cache(path: Path) -> dict[str, list[float]]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("geocode cache corrupted, starting fresh")
    return {}


def _save_cache(cache: dict[str, list[float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache), encoding="utf-8")


def _live_geocoder(cfg: dict[str, Any]):
    """Lazy-build the geopy geocoder so the import is optional in CI."""
    from geopy.geocoders import Nominatim, GoogleV3
    from geopy.extra.rate_limiter import RateLimiter

    g_cfg = cfg["geocoding"]
    if g_cfg["provider"] == "google" and g_cfg.get("google_api_key"):
        geocoder = GoogleV3(api_key=g_cfg["google_api_key"], timeout=15)
    else:
        geocoder = Nominatim(user_agent=g_cfg["user_agent"], timeout=15)
    return RateLimiter(geocoder.geocode, min_delay_seconds=g_cfg["rate_limit_seconds"], swallow_exceptions=True)


def geocode_dataframe(clean_path: str | Path, cfg: dict[str, Any], live: bool = False) -> Path:
    df = read_any(clean_path)
    cache_path = project_path(cfg["geocoding"]["cache_path"])
    cache = _load_cache(cache_path)

    lats: list[float | None] = []
    lons: list[float | None] = []

    geocode = None
    if live:
        try:
            geocode = _live_geocoder(cfg)
            log.info("live geocoding ENABLED (provider=%s)", cfg["geocoding"]["provider"])
        except Exception as exc:
            log.warning("could not build live geocoder (%s) — using ZIP-centroid fallback", exc)
            geocode = None

    for i, row in enumerate(df.itertuples(index=False), start=1):
        addr = getattr(row, "full_address", None)
        zip_code = getattr(row, "zip_code", None)
        key = (addr or "").strip().lower()

        if key in cache:
            lats.append(cache[key][0])
            lons.append(cache[key][1])
            continue

        lat = lon = None
        if geocode and addr:
            try:
                loc = geocode(addr)
                if loc is not None:
                    lat, lon = loc.latitude, loc.longitude
            except Exception as exc:
                log.warning("geocode failed for %s: %s", addr, exc)
                time.sleep(0.5)

        if lat is None or lon is None:
            lat, lon = _approx_centroid(zip_code)

        lats.append(lat)
        lons.append(lon)
        if addr and lat is not None and lon is not None:
            cache[key] = [lat, lon]

        if i % 500 == 0:
            log.info("geocoded %d/%d", i, len(df))
            _save_cache(cache, cache_path)

    _save_cache(cache, cache_path)
    df["latitude"] = lats
    df["longitude"] = lons

    out_stem = project_path(cfg["paths"]["interim_dir"], "nj_housing_geocoded")
    written = write_dataframe(df, out_stem, csv=False, parquet=True)
    log.info("geocoded: %d rows → %s", len(df), written["parquet"])
    return written["parquet"]
