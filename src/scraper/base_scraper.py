"""Base scraper.

Provides a thin requests wrapper with:
  - rotating User-Agent pool
  - polite rate limit
  - exponential backoff retry (tenacity)
  - structured error logging

All county-level scrapers subclass `BaseScraper` and implement `fetch_county()`.
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils.logger import get_logger

log = get_logger(__name__)


class ScrapeBlockedError(RuntimeError):
    """Raised when the source has clearly blocked us (403 / 429 / captcha)."""


@dataclass
class Listing:
    """Canonical raw-listing record. Matches the columns required by Phase 1."""
    listing_price: float | None = None
    full_address: str | None = None
    zip_code: str | None = None
    county: str | None = None
    municipality: str | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    sqft: float | None = None
    property_type: str | None = None
    listing_url: str | None = None
    scrape_timestamp: str | None = None
    lot_size: float | None = None
    year_built: int | None = None
    days_on_market: int | None = None
    hoa_fees: float | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BaseScraper(ABC):
    name: str = "base"
    user_agents: list[str] = field(default_factory=list)
    rate_limit_seconds: float = 2.5
    timeout_seconds: int = 20
    max_retries: int = 3
    backoff_factor: float = 2.0

    _last_request_ts: float = field(default=0.0, init=False, repr=False)
    session: requests.Session = field(default_factory=requests.Session, init=False, repr=False)

    # ------- public API -------------------------------------------------
    @abstractmethod
    def fetch_county(self, county: str) -> list[Listing]:
        """Return a list of Listing objects for a given NJ county."""
        ...

    # ------- helpers ----------------------------------------------------
    def _ua(self) -> str:
        return random.choice(self.user_agents) if self.user_agents else "Mozilla/5.0"

    def _polite_sleep(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_ts = time.time()

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Polite GET with retries. Raises ScrapeBlockedError on 403/429."""

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_factor, min=2, max=30),
            retry=retry_if_exception_type((requests.RequestException,)),
            reraise=True,
        )
        def _inner() -> requests.Response:
            self._polite_sleep()
            headers = {"User-Agent": self._ua(), "Accept-Language": "en-US,en;q=0.9"}
            headers.update(kwargs.pop("headers", {}))
            log.debug("[%s] GET %s", self.name, url)
            resp = self.session.get(url, headers=headers, timeout=self.timeout_seconds, **kwargs)
            if resp.status_code in (403, 429):
                log.warning("[%s] blocked (HTTP %s) on %s", self.name, resp.status_code, url)
                raise ScrapeBlockedError(f"{self.name} blocked: HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp

        return _inner()
