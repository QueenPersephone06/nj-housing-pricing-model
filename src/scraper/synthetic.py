"""Synthetic NJ listings generator.

Used when `--scrape 0` is passed, or when all three live sources fail.
Generates ~6,000 plausible NJ listings spread across all 21 counties,
with empirically-calibrated medians (e.g., Bergen ~$700k, Cumberland
~$220k, Hudson ~$650k, Sussex ~$370k).

Outputs the same canonical Listing schema as the live scrapers so the
downstream pipeline is identical.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.scraper.base_scraper import Listing
from src.utils.logger import get_logger

log = get_logger(__name__)

# Empirically calibrated county medians (rough 2024 single-family medians, USD)
COUNTY_PRICE_MEDIAN: dict[str, int] = {
    "Atlantic": 320_000,
    "Bergen": 720_000,
    "Burlington": 360_000,
    "Camden": 270_000,
    "Cape May": 580_000,
    "Cumberland": 220_000,
    "Essex": 540_000,
    "Gloucester": 310_000,
    "Hudson": 660_000,
    "Hunterdon": 540_000,
    "Mercer": 410_000,
    "Middlesex": 470_000,
    "Monmouth": 600_000,
    "Morris": 620_000,
    "Ocean": 430_000,
    "Passaic": 470_000,
    "Salem": 210_000,
    "Somerset": 580_000,
    "Sussex": 370_000,
    "Union": 520_000,
    "Warren": 360_000,
}

# Sample municipalities per county (representative, not exhaustive)
COUNTY_MUNICIPALITIES: dict[str, list[str]] = {
    "Atlantic": ["Atlantic City", "Egg Harbor Township", "Hammonton", "Galloway", "Pleasantville"],
    "Bergen": ["Hackensack", "Paramus", "Fort Lee", "Englewood", "Teaneck", "Ridgewood", "Fair Lawn"],
    "Burlington": ["Mount Laurel", "Willingboro", "Burlington", "Evesham", "Moorestown"],
    "Camden": ["Camden", "Cherry Hill", "Voorhees", "Gloucester Township", "Pennsauken"],
    "Cape May": ["Cape May", "Ocean City", "Wildwood", "Stone Harbor", "Avalon"],
    "Cumberland": ["Vineland", "Millville", "Bridgeton", "Vineland City"],
    "Essex": ["Newark", "Montclair", "East Orange", "Bloomfield", "West Orange", "Livingston"],
    "Gloucester": ["Washington Township", "Deptford", "Glassboro", "Monroe", "West Deptford"],
    "Hudson": ["Jersey City", "Hoboken", "Union City", "West New York", "Bayonne", "North Bergen"],
    "Hunterdon": ["Flemington", "Clinton", "Lambertville", "Readington", "Tewksbury"],
    "Mercer": ["Trenton", "Princeton", "Hamilton", "Ewing", "West Windsor", "Lawrence"],
    "Middlesex": ["New Brunswick", "Edison", "Woodbridge", "Piscataway", "East Brunswick", "Old Bridge"],
    "Monmouth": ["Long Branch", "Asbury Park", "Middletown", "Freehold", "Red Bank", "Manalapan"],
    "Morris": ["Morristown", "Parsippany", "Madison", "Chatham", "Mendham", "Randolph"],
    "Ocean": ["Toms River", "Brick", "Lakewood", "Jackson", "Manchester", "Point Pleasant"],
    "Passaic": ["Paterson", "Clifton", "Passaic", "Wayne", "Hawthorne"],
    "Salem": ["Salem", "Pennsville", "Carneys Point", "Penns Grove"],
    "Somerset": ["Somerville", "Bridgewater", "Franklin", "Hillsborough", "Bernards"],
    "Sussex": ["Newton", "Sparta", "Vernon", "Hopatcong", "Hardyston"],
    "Union": ["Elizabeth", "Union", "Plainfield", "Westfield", "Summit", "Cranford"],
    "Warren": ["Phillipsburg", "Hackettstown", "Washington", "Mansfield"],
}

# Representative ZIP per county (one or two) — synthesizer randomly picks
COUNTY_ZIPS: dict[str, list[str]] = {
    "Atlantic": ["08401", "08234", "08037", "08205", "08232"],
    "Bergen": ["07601", "07652", "07024", "07631", "07666", "07450", "07410"],
    "Burlington": ["08054", "08046", "08016", "08053", "08057"],
    "Camden": ["08105", "08003", "08043", "08012", "08109"],
    "Cape May": ["08204", "08226", "08260", "08247", "08202"],
    "Cumberland": ["08360", "08332", "08302"],
    "Essex": ["07102", "07042", "07017", "07003", "07052", "07039"],
    "Gloucester": ["08080", "08096", "08028", "08094", "08086"],
    "Hudson": ["07302", "07030", "07087", "07093", "07002", "07047"],
    "Hunterdon": ["08822", "08809", "08530", "08889", "07830"],
    "Mercer": ["08618", "08540", "08619", "08628", "08550", "08648"],
    "Middlesex": ["08901", "08820", "07095", "08854", "08816", "08857"],
    "Monmouth": ["07740", "07712", "07748", "07728", "07701", "07726"],
    "Morris": ["07960", "07054", "07940", "07928", "07945", "07869"],
    "Ocean": ["08753", "08723", "08701", "08527", "08759", "08742"],
    "Passaic": ["07501", "07011", "07055", "07470", "07506"],
    "Salem": ["08079", "08070", "08069"],
    "Sussex": ["07860", "07871", "07462", "07843", "07419"],
    "Somerset": ["08876", "08807", "08873", "08844", "07920"],
    "Union": ["07201", "07083", "07060", "07090", "07901", "07016"],
    "Warren": ["08865", "07840", "07882", "07840"],
}

PROPERTY_TYPES = ["Single Family", "Condo/Co-op", "Townhouse", "Multi-Family", "Land"]
PROPERTY_TYPE_WEIGHTS = [0.62, 0.18, 0.10, 0.07, 0.03]


def _street_name(idx: int) -> str:
    syllables = ["Oak", "Maple", "Cedar", "Pine", "Elm", "Birch", "Willow", "Lake", "Park", "River", "Forest", "Hill", "Spring", "Highland", "Main", "Washington", "Lincoln", "Madison", "Jefferson", "Garden"]
    suffixes = ["St", "Ave", "Rd", "Ln", "Ct", "Blvd", "Dr", "Way", "Pl"]
    return f"{(idx * 37) % 9000 + 100} {syllables[idx % len(syllables)]} {suffixes[idx % len(suffixes)]}"


def generate_listings(
    counties: list[str],
    per_county_target: int = 285,
    seed: int = 42,
) -> list[Listing]:
    """Generate ~per_county_target × 21 ≈ 6,000 listings."""
    rng = np.random.default_rng(seed)
    random.seed(seed)
    out: list[Listing] = []
    now = datetime.utcnow()

    for county in counties:
        base_median = COUNTY_PRICE_MEDIAN.get(county, 400_000)
        n = int(rng.normal(per_county_target, 25))
        n = max(120, n)  # ensure every county has enough rows for downstream filters
        zips = COUNTY_ZIPS[county]
        munis = COUNTY_MUNICIPALITIES[county]

        for i in range(n):
            ptype = random.choices(PROPERTY_TYPES, weights=PROPERTY_TYPE_WEIGHTS, k=1)[0]

            # Property-type-specific feature draws
            if ptype == "Land":
                beds = 0
                baths = 0
                sqft_real = 0.0
                sqft = None
                lot_size = float(rng.integers(5000, 200_000))
                year_built = None
                hoa = None
                type_mult = 0.25
                age_premium = 1.0
            elif ptype == "Condo/Co-op":
                beds = int(np.clip(rng.normal(2.0, 0.8), 0, 4))
                baths = float(np.clip(rng.normal(2.0, 0.6), 1, 4))
                sqft_real = float(np.clip(rng.normal(1100, 350), 500, 3000))
                sqft = sqft_real
                lot_size = None
                year_built = int(np.clip(rng.normal(1995, 18), 1900, 2024))
                hoa = float(np.clip(rng.normal(400, 150), 100, 1500))
                type_mult = 0.90
                age_premium = 1.0 + max(0, (year_built - 1960)) * 0.0025
            elif ptype == "Townhouse":
                beds = int(np.clip(rng.normal(3.0, 0.7), 2, 5))
                baths = float(np.clip(rng.normal(2.5, 0.6), 1.5, 4.5))
                sqft_real = float(np.clip(rng.normal(1700, 400), 900, 3500))
                sqft = sqft_real
                lot_size = float(np.clip(rng.normal(2500, 800), 1000, 6000))
                year_built = int(np.clip(rng.normal(2000, 15), 1900, 2024))
                hoa = float(np.clip(rng.normal(250, 120), 50, 600))
                type_mult = 0.95
                age_premium = 1.0 + max(0, (year_built - 1960)) * 0.0025
            elif ptype == "Multi-Family":
                beds = int(np.clip(rng.normal(5.0, 1.5), 2, 10))
                baths = float(np.clip(rng.normal(3.0, 1.2), 2, 7))
                sqft_real = float(np.clip(rng.normal(2800, 800), 1500, 6000))
                sqft = sqft_real
                lot_size = float(np.clip(rng.normal(4500, 1500), 2000, 15000))
                year_built = int(np.clip(rng.normal(1955, 25), 1880, 2024))
                hoa = None
                type_mult = 1.15
                age_premium = 1.0 + max(0, (year_built - 1960)) * 0.0020
            else:  # Single Family
                beds = int(np.clip(rng.normal(3.4, 1.0), 1, 7))
                baths = float(np.clip(rng.normal(2.5, 0.8), 1, 6))
                sqft_real = float(np.clip(rng.normal(2000, 650), 700, 6000))
                sqft = sqft_real
                lot_size = float(np.clip(rng.normal(8500, 5000), 1500, 80000))
                year_built = int(np.clip(rng.normal(1975, 25), 1880, 2024))
                hoa = None if rng.random() < 0.85 else float(np.clip(rng.normal(150, 80), 30, 500))
                type_mult = 1.00
                age_premium = 1.0 + max(0, (year_built - 1960)) * 0.0030

            # Price is a hedonic function of features + county fixed effect + log-normal noise.
            # County price ≈ price per "standard" home (3br/2ba/2000 sqft).
            if ptype == "Land":
                price = base_median * 0.25 * (lot_size / 10000) ** 0.5
                price *= np.exp(rng.normal(0, 0.35))
            else:
                # Reference 2000 sqft, 3 br, 2 ba, 1990 build
                sqft_factor = (sqft_real / 2000.0) ** 0.85
                bed_factor = 1.0 + 0.06 * (beds - 3)
                bath_factor = 1.0 + 0.05 * (baths - 2)
                price = (base_median * type_mult
                         * sqft_factor * bed_factor * bath_factor * age_premium)
                price *= np.exp(rng.normal(0, 0.18))  # ~18% noise
            price = max(50_000, price)

            # Tiny chance of a real outlier (cleaning phase will catch)
            if rng.random() < 0.002:
                price *= 30  # ultra-luxury / data-quality test

            zip_code = random.choice(zips)
            muni = random.choice(munis)
            address = f"{_street_name(len(out))}, {muni}, NJ {zip_code}"

            # Random missingness (~5-10%)
            if rng.random() < 0.07:
                sqft = None
            if rng.random() < 0.04:
                beds = None
            if rng.random() < 0.04:
                baths = None

            dom = int(np.clip(rng.exponential(35), 0, 400))
            ts = (now - timedelta(minutes=int(rng.integers(0, 60 * 24 * 14)))).isoformat(timespec="seconds")
            uid = hashlib.md5(f"{county}{i}{address}".encode()).hexdigest()[:10]

            out.append(
                Listing(
                    listing_price=round(float(price), -2),  # round to nearest hundred
                    full_address=address,
                    zip_code=zip_code,
                    county=county,
                    municipality=muni,
                    bedrooms=beds,
                    bathrooms=baths,
                    sqft=round(sqft, 0) if sqft else None,
                    property_type=ptype,
                    listing_url=f"https://synthetic.local/listing/{uid}",
                    scrape_timestamp=ts,
                    lot_size=round(lot_size, 0) if lot_size else None,
                    year_built=year_built,
                    days_on_market=dom,
                    hoa_fees=round(hoa, 0) if hoa else None,
                    source="synthetic",
                )
            )

    log.info("synthetic generator produced %d listings across %d counties", len(out), len(counties))
    return out


def listings_to_dataframe(listings: list[Listing]) -> pd.DataFrame:
    return pd.DataFrame([l.as_dict() for l in listings])
