"""Zillow scraper — PRIMARY source.

Strategy
--------
Zillow exposes a JSON endpoint behind the search-results page that returns a
paginated list of "homes" for any region. We hit that endpoint (rather than
parsing the dense React-rendered HTML) and walk pages until empty.

The selectors live in PARSERS at the top so they can be hot-patched if
Zillow changes their schema.

Note: Zillow aggressively challenges automated traffic. On 403/429 the
orchestrator will fail us over to Realtor.com.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from src.scraper.base_scraper import BaseScraper, Listing, ScrapeBlockedError
from src.utils.logger import get_logger

log = get_logger(__name__)

PARSERS = {
    "search_url": "https://www.zillow.com/search/GetSearchPageState.htm",
    "results_path": ["cat1", "searchResults", "listResults"],
    "fields": {
        "listing_price": ("unformattedPrice",),
        "full_address": ("address",),
        "zip_code": ("addressZipcode",),
        "bedrooms": ("beds",),
        "bathrooms": ("baths",),
        "sqft": ("area",),
        "property_type": ("hdpData", "homeInfo", "homeType"),
        "listing_url": ("detailUrl",),
        "lot_size": ("hdpData", "homeInfo", "lotAreaValue"),
        "year_built": ("hdpData", "homeInfo", "yearBuilt"),
        "days_on_market": ("hdpData", "homeInfo", "daysOnZillow"),
    },
}


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        else:
            return None
    return obj


class ZillowScraper(BaseScraper):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="zillow", **kwargs)

    def fetch_county(self, county: str) -> list[Listing]:
        log.info("[zillow] fetching %s County, NJ", county)
        listings: list[Listing] = []
        page = 1
        while True:
            params = {
                "searchQueryState": json.dumps(
                    {
                        "usersSearchTerm": f"{county} County NJ",
                        "filterState": {"sortSelection": {"value": "globalrelevanceex"}},
                        "isListVisible": True,
                        "pagination": {"currentPage": page},
                    }
                ),
                "wants": json.dumps({"cat1": ["listResults"]}),
                "requestId": str(page),
            }
            url = f"{PARSERS['search_url']}?{urlencode(params)}"
            try:
                resp = self.get(url, headers={"Accept": "application/json"})
                data = resp.json()
            except ScrapeBlockedError:
                raise
            except Exception as exc:
                log.error("[zillow] failed page %s in %s: %s", page, county, exc)
                break

            results = _dig(data, tuple(PARSERS["results_path"])) or []
            if not results:
                break

            for r in results:
                listings.append(self._parse(r, county))

            if len(results) < 40:  # last page heuristic
                break
            page += 1
            if page > 20:  # safety cap
                break

        log.info("[zillow] %s County → %d listings", county, len(listings))
        return listings

    def _parse(self, record: dict[str, Any], county: str) -> Listing:
        f = PARSERS["fields"]
        return Listing(
            listing_price=_dig(record, f["listing_price"]),
            full_address=_dig(record, f["full_address"]),
            zip_code=str(_dig(record, f["zip_code"]) or "").zfill(5) or None,
            county=county,
            municipality=None,  # derived later from address parsing
            bedrooms=_dig(record, f["bedrooms"]),
            bathrooms=_dig(record, f["bathrooms"]),
            sqft=_dig(record, f["sqft"]),
            property_type=_dig(record, f["property_type"]),
            listing_url=_dig(record, f["listing_url"]),
            scrape_timestamp=datetime.utcnow().isoformat(timespec="seconds"),
            lot_size=_dig(record, f["lot_size"]),
            year_built=_dig(record, f["year_built"]),
            days_on_market=_dig(record, f["days_on_market"]),
            hoa_fees=None,  # not in list view; would need DPP page
            source="zillow",
        )
