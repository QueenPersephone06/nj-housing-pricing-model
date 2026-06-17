"""Redfin scraper — SECOND FALLBACK.

Redfin exposes a JSON gateway at /stingray/api/gis-csv that returns a CSV
of all listings within a region. We discover the region_id via the
/stingray/do/location-autocomplete endpoint, then download the CSV.

If Redfin is also blocked, we abort the live-scrape path and the
orchestrator will optionally fall back to the synthetic generator.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from src.scraper.base_scraper import BaseScraper, Listing, ScrapeBlockedError
from src.utils.logger import get_logger

log = get_logger(__name__)

PARSERS = {
    "autocomplete_url": "https://www.redfin.com/stingray/do/location-autocomplete",
    "gis_csv_url": "https://www.redfin.com/stingray/api/gis-csv",
    "csv_cols": {
        "listing_price": "PRICE",
        "full_address": "ADDRESS",
        "zip_code": "ZIP OR POSTAL CODE",
        "municipality": "CITY",
        "bedrooms": "BEDS",
        "bathrooms": "BATHS",
        "sqft": "SQUARE FEET",
        "property_type": "PROPERTY TYPE",
        "listing_url": "URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)",
        "lot_size": "LOT SIZE",
        "year_built": "YEAR BUILT",
        "days_on_market": "DAYS ON MARKET",
        "hoa_fees": "HOA/MONTH",
    },
}


class RedfinScraper(BaseScraper):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="redfin", **kwargs)

    def _resolve_region_id(self, county: str) -> int | None:
        params = {"location": f"{county} County, NJ", "v": 2}
        resp = self.get(PARSERS["autocomplete_url"], params=params)
        # Redfin prepends {}& as anti-script measure
        body = resp.text.lstrip("{}&")
        import json as _json

        try:
            data = _json.loads(body)
        except _json.JSONDecodeError:
            return None
        sections = data.get("payload", {}).get("sections", [])
        for sec in sections:
            for row in sec.get("rows", []):
                if "County" in (row.get("name") or "") and "NJ" in (row.get("subName") or ""):
                    return int(row.get("id", "").split("_")[-1])
        return None

    def fetch_county(self, county: str) -> list[Listing]:
        log.info("[redfin] fetching %s County, NJ", county)
        region_id = self._resolve_region_id(county)
        if region_id is None:
            log.warning("[redfin] could not resolve region for %s", county)
            return []
        params = {
            "al": 1,
            "market": "newjersey",
            "num_homes": 5000,
            "ord": "redfin-recommended-asc",
            "page_number": 1,
            "region_id": region_id,
            "region_type": 5,  # county
            "status": 9,
            "uipt": "1,2,3,4,5,6",
            "v": 8,
        }
        try:
            resp = self.get(PARSERS["gis_csv_url"], params=params)
        except ScrapeBlockedError:
            raise

        listings: list[Listing] = []
        reader = csv.DictReader(io.StringIO(resp.text))
        cols = PARSERS["csv_cols"]
        for row in reader:
            listings.append(
                Listing(
                    listing_price=_num(row.get(cols["listing_price"])),
                    full_address=row.get(cols["full_address"]),
                    zip_code=str(row.get(cols["zip_code"]) or "").zfill(5) or None,
                    county=county,
                    municipality=row.get(cols["municipality"]),
                    bedrooms=_num(row.get(cols["bedrooms"])),
                    bathrooms=_num(row.get(cols["bathrooms"])),
                    sqft=_num(row.get(cols["sqft"])),
                    property_type=row.get(cols["property_type"]),
                    listing_url=row.get(cols["listing_url"]),
                    scrape_timestamp=datetime.utcnow().isoformat(timespec="seconds"),
                    lot_size=_num(row.get(cols["lot_size"])),
                    year_built=_int(row.get(cols["year_built"])),
                    days_on_market=_int(row.get(cols["days_on_market"])),
                    hoa_fees=_num(row.get(cols["hoa_fees"])),
                    source="redfin",
                )
            )
        log.info("[redfin] %s County → %d listings", county, len(listings))
        return listings


def _num(v: Any) -> float | None:
    if v in (None, "", "—"):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None
