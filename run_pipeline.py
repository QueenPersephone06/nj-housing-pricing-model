"""End-to-end NJ Housing pipeline runner.

Usage
-----
    python run_pipeline.py --scrape 0       # offline / synthetic
    python run_pipeline.py --scrape 1       # live scrape (Zillow → Realtor → Redfin)
    python run_pipeline.py --geocode 1      # enable live geocoding (slow)

Runs all 10 phases end-to-end.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from src.cleaning.clean import clean_data
from src.geocoding.geocode import geocode_dataframe
from src.modeling.clustering import cluster_listings
from src.modeling.hedonic_model import train_hedonic
from src.pricing.pricing_analytics import compute_pricing_analytics
from src.reporting.deck import build_deck
from src.scraper.orchestrator import run_scrape
from src.segmentation.segment import segment
from src.utils.io import load_config
from src.utils.logger import get_logger
from src.visualization.charts import make_all_charts
from src.visualization.map import build_map

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="NJ Housing — full pipeline")
    parser.add_argument("--scrape", type=int, default=0, help="1 = live scrape, 0 = synthetic")
    parser.add_argument("--geocode", type=int, default=0, help="1 = live geopy/Nominatim, 0 = ZIP-centroid fallback")
    parser.add_argument("--config", type=str, default="config/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    start = time.time()

    # Phase 1
    log.info("───── Phase 1: SCRAPE ─────")
    raw_path = run_scrape(cfg, live=bool(args.scrape))

    # Phase 2
    log.info("───── Phase 2: CLEAN ─────")
    clean_path, metrics = clean_data(raw_path, cfg)
    log.info("clean metrics: %s", metrics)

    # Phase 3
    log.info("───── Phase 3: GEOCODE ─────")
    geocoded_path = geocode_dataframe(clean_path, cfg, live=bool(args.geocode))

    # Phase 4
    log.info("───── Phase 4: SEGMENT ─────")
    segmented_path = segment(geocoded_path, cfg)

    # Phase 5
    log.info("───── Phase 5: PRICING ANALYTICS ─────")
    pricing_outputs = compute_pricing_analytics(segmented_path, cfg)

    # Phase 6
    log.info("───── Phase 6: HEDONIC MODEL ─────")
    model_results = train_hedonic(segmented_path, cfg)
    log.info("model results: %s", model_results)

    # Phase 7
    log.info("───── Phase 7: CLUSTERING ─────")
    cluster_listings(segmented_path, cfg)

    # Phase 8
    log.info("───── Phase 8: CHARTS ─────")
    make_all_charts(segmented_path, cfg)

    # Phase 9
    log.info("───── Phase 9: MAP ─────")
    build_map(segmented_path, cfg)

    # Phase 10
    log.info("───── Phase 10: DECK ─────")
    build_deck(cfg)

    elapsed = time.time() - start
    log.info("PIPELINE COMPLETE in %.1fs", elapsed)


if __name__ == "__main__":
    main()
