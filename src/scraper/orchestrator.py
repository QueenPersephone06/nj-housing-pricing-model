"""Orchestrator — runs the primary scraper, falls back per-county.

Failover policy (per county):
    Zillow → Realtor.com → Redfin → (fail = skip with WARN)

The result is concatenated, deduplicated by (address, zip), and written
to data/raw/nj_housing_raw_<ts>.csv  + .parquet.

If `--scrape 0` is passed via the CLI, the synthetic generator is used
instead and labelled `source=synthetic`.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.scraper.base_scraper import BaseScraper, Listing, ScrapeBlockedError
from src.scraper.realtor_scraper import RealtorScraper
from src.scraper.redfin_scraper import RedfinScraper
from src.scraper.synthetic import generate_listings, listings_to_dataframe
from src.scraper.zillow_scraper import ZillowScraper
from src.utils.io import project_path, write_dataframe
from src.utils.logger import get_logger

log = get_logger(__name__)


def _build_scrapers(cfg: dict[str, Any]) -> list[BaseScraper]:
    common: dict[str, Any] = {
        "user_agents": cfg["scraper"]["user_agents"],
        "rate_limit_seconds": cfg["scraper"]["rate_limit_seconds"],
        "timeout_seconds": cfg["scraper"]["timeout_seconds"],
        "max_retries": cfg["scraper"]["max_retries"],
        "backoff_factor": cfg["scraper"]["backoff_factor"],
    }
    return [ZillowScraper(**common), RealtorScraper(**common), RedfinScraper(**common)]


def _county_with_failover(scrapers: list[BaseScraper], county: str) -> list[Listing]:
    last_err: Exception | None = None
    for scr in scrapers:
        try:
            rows = scr.fetch_county(county)
            if rows:
                return rows
            log.warning("[%s] returned 0 rows for %s — trying next source", scr.name, county)
        except ScrapeBlockedError as exc:
            log.warning("[%s] blocked on %s — falling over: %s", scr.name, county, exc)
            last_err = exc
        except Exception as exc:
            log.exception("[%s] unexpected error on %s — falling over", scr.name, county)
            last_err = exc
    log.error("ALL sources failed for %s (last error: %s)", county, last_err)
    return []


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_dupe_key"] = (df["full_address"].fillna("") + "|" + df["zip_code"].fillna("")).apply(
        lambda s: hashlib.md5(s.lower().encode()).hexdigest()
    )
    before = len(df)
    df = df.drop_duplicates(subset="_dupe_key").drop(columns="_dupe_key")
    log.info("deduplication: %d → %d rows", before, len(df))
    return df


def run_scrape(cfg: dict[str, Any], live: bool = True) -> Path:
    counties: list[str] = cfg["counties"]
    if live:
        log.info("LIVE scrape across %d NJ counties", len(counties))
        scrapers = _build_scrapers(cfg)
        all_rows: list[Listing] = []
        for c in counties:
            all_rows.extend(_county_with_failover(scrapers, c))
        if not all_rows:
            log.warning("Live scrape returned 0 rows — falling back to synthetic generator")
            all_rows = generate_listings(counties, seed=cfg["random_seed"])
        df = pd.DataFrame([l.as_dict() for l in all_rows])
    else:
        log.info("OFFLINE mode — generating synthetic NJ listings")
        df = listings_to_dataframe(generate_listings(counties, seed=cfg["random_seed"]))

    df = _dedupe(df)

    # price_per_sqft
    df["price_per_sqft"] = df["listing_price"] / df["sqft"].replace(0, pd.NA)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    stem = project_path(cfg["paths"]["raw_dir"], f"nj_housing_raw_{ts}")
    outputs = write_dataframe(df, stem, csv=True, parquet=True)
    log.info("wrote raw scrape: %s", outputs)
    return outputs["parquet"]
