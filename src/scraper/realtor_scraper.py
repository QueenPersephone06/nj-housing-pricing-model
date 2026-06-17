"""Realtor.com scraper — FIRST FALLBACK.

Uses the public /realestateandhomes-search/<County>_NJ HTML route and
extracts the embedded __NEXT_DATA__ JSON blob (Next.js apps inline their
initial server state, so we don't have to scrape the rendered DOM).

If Realtor blocks us, the orchestrator falls through to Redfin.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from src.scraper.base_scraper import BaseScraper, Listing, ScrapeBlockedError
from src.utils.logger import get_logger

log = get_logger(__name__)

PARSERS = {
    "url_template": "https://www.realtor.com/realestateandhomes-search/{county}-County_NJ/pg-{page}",
    "next_data_id": "__NEXT_DATA__",
    "results_path": ("props", "pageProps", "properties"),
}


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        else:
            return None
    return obj


class RealtorScraper(BaseScraper):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="realtor", **kwargs)

    def fetch_county(self, county: str) -> list[Listing]:
        log.info("[realtor] fetching %s County, NJ", county)
        listings: list[Listing] = []
        slug = county.replace(" ", "-")
        for page in range(1, 21):
            url = PARSERS["url_template"].format(county=slug, page=page)
            try:
                resp = self.get(url)
            except ScrapeBlockedError:
                raise
            except Exception as exc:
                log.error("[realtor] page %s in %s failed: %s", page, county, exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            blob = soup.find("script", id=PARSERS["next_data_id"])
            if not blob:
                break
            try:
                data = json.loads(blob.string or "{}")
            except json.JSONDecodeError:
                break

            results = _dig(data, PARSERS["results_path"]) or []
            if not results:
                break
            for r in results:
                listings.append(self._parse(r, county))
            if len(results) < 40:
                break

        log.info("[realtor] %s County → %d listings", county, len(listings))
        return listings

    def _parse(self, record: dict[str, Any], county: str) -> Listing:
        loc = record.get("location") or {}
        addr = loc.get("address") or {}
        desc = record.get("description") or {}
        full_addr_parts = [addr.get("line"), addr.get("city"), addr.get("state_code"), addr.get("postal_code")]
        full_address = ", ".join(p for p in full_addr_parts if p)

        return Listing(
            listing_price=record.get("list_price"),
            full_address=full_address,
            zip_code=str(addr.get("postal_code") or "").zfill(5) or None,
            county=county,
            municipality=addr.get("city"),
            bedrooms=desc.get("beds"),
            bathrooms=desc.get("baths"),
            sqft=desc.get("sqft"),
            property_type=desc.get("type"),
            listing_url=f"https://www.realtor.com/realestateandhomes-detail/{record.get('permalink','')}",
            scrape_timestamp=datetime.utcnow().isoformat(timespec="seconds"),
            lot_size=desc.get("lot_sqft"),
            year_built=desc.get("year_built"),
            days_on_market=record.get("list_date") and _days_on_market(record["list_date"]),
            hoa_fees=(record.get("hoa") or {}).get("fee"),
            source="realtor",
        )


def _days_on_market(list_date_iso: str) -> int | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", list_date_iso)
    if not m:
        return None
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return max(0, (datetime.utcnow() - d).days)
    except ValueError:
        return None
