# NJ Housing Market — Scraper & Pricing Model

End-to-end data science project covering active residential listings across **all 21 New Jersey counties**. The pipeline scrapes listings (Zillow → Realtor.com → Redfin fallback), cleans and geocodes them, segments micro-markets (county → municipality → ZIP cluster), runs hedonic pricing and K-Means clustering, and produces an interactive Folium choropleth, a pricing matrix, model evaluation, a data-quality report, and an executive summary deck.

---

## 1. Quick Start

```bash
# 1. Clone and enter
git clone <repo-url> nj-housing-pricing-model
cd nj-housing-pricing-model

# 2. Create a virtual env (Python 3.10+)
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 3. Install
pip install -r requirements.txt

# 4. Run the full pipeline (uses synthetic NJ data if SCRAPE=0)
python run_pipeline.py --scrape 0       # offline, synthetic-data demo run
python run_pipeline.py --scrape 1       # live scrape (Zillow → Realtor → Redfin)
```

All outputs land in `data/processed/`, `outputs/`, and `reports/`.

---

## 2. Project Structure

```
nj-housing-pricing-model/
├── README.md
├── requirements.txt
├── run_pipeline.py                    # one-shot orchestrator (all 10 phases)
├── config/
│   └── config.yaml                    # counties, paths, model params, rate-limits
├── data/
│   ├── raw/                           # scraper output (CSV + Parquet, timestamped)
│   ├── interim/                       # cleaned, geocoded
│   ├── processed/                     # segmented + pricing analytics
│   └── external/                      # NJ county GeoJSON, ZIP→County crosswalk
├── src/
│   ├── scraper/                       # Phase 1
│   │   ├── base_scraper.py            # rate-limit, retries, UA rotation
│   │   ├── zillow_scraper.py
│   │   ├── realtor_scraper.py
│   │   ├── redfin_scraper.py
│   │   ├── orchestrator.py            # source failover logic
│   │   └── synthetic.py               # offline data generator (covers 21 counties)
│   ├── cleaning/clean.py              # Phase 2
│   ├── geocoding/geocode.py           # Phase 3 (geopy + cache)
│   ├── segmentation/segment.py        # Phase 4 (county / muni / ZIP cluster / corridor)
│   ├── pricing/pricing_analytics.py   # Phase 5 (medians, heat index, pricing matrix)
│   ├── modeling/
│   │   ├── hedonic_model.py           # Phase 6 (Linear + Ridge)
│   │   └── clustering.py              # Phase 7 (K-Means tiers)
│   ├── visualization/
│   │   ├── charts.py                  # Phase 8 (matplotlib / seaborn / plotly)
│   │   └── map.py                     # Phase 9 (Folium choropleth)
│   └── utils/{logger.py, io.py}
├── notebooks/
│   └── NJ_Housing_Analysis.ipynb      # end-to-end walkthrough
├── reports/
│   ├── data_quality_report.md
│   ├── model_evaluation_report.md
│   ├── summary_deck.pptx              # 8-slide executive deck
│   └── figures/                       # all PNG charts
├── outputs/
│   ├── pricing_matrix.csv             # micro-market × (beds × prop type) median price
│   ├── nj_housing_map.html            # interactive Folium choropleth
│   └── models/                        # joblib-pickled Linear + Ridge
├── tests/                             # pytest unit tests
└── logs/                              # rotating run logs
```

---

## 3. Phase-by-Phase Overview

| Phase | Module | Output |
|-------|--------|--------|
| 1. Scrape | `src/scraper/orchestrator.py` | `data/raw/nj_housing_raw_<ts>.{csv,parquet}` |
| 2. Clean | `src/cleaning/clean.py` | `data/interim/nj_housing_clean.parquet` + `reports/data_quality_report.md` |
| 3. Geocode | `src/geocoding/geocode.py` | `data/interim/nj_housing_geocoded.parquet` |
| 4. Segment | `src/segmentation/segment.py` | adds `zip_cluster`, `corridor` cols |
| 5. Pricing analytics | `src/pricing/pricing_analytics.py` | `data/processed/pricing_by_*.csv`, `outputs/pricing_matrix.csv` |
| 6. Hedonic ML | `src/modeling/hedonic_model.py` | `outputs/models/{linreg,ridge}.joblib` + `reports/model_evaluation_report.md` |
| 7. Clustering | `src/modeling/clustering.py` | `data/processed/listings_with_tier.parquet` + elbow + scatter PNGs |
| 8. Charts | `src/visualization/charts.py` | `reports/figures/*.png` (county bar, histograms, heatmap, corr matrix, etc.) |
| 9. Map | `src/visualization/map.py` | `outputs/nj_housing_map.html` |
| 10. Deck | `src/reporting/deck.py` | `reports/summary_deck.pptx` |

---

## 4. Data Sources & Failover

The scraper tries **Zillow** first. On HTTP 403/429 or empty response it falls through to **Realtor.com**, then **Redfin**. Failover is per-county, so partial scrape success is preserved. All three scrapers share `base_scraper.BaseScraper` (rate limit ≥ 2 s between requests, exponential backoff retry × 3, rotating UA pool of 8, error logging to `logs/scraper.log`, duplicate detection by `(address, zip)` hash).

If you cannot scrape (corporate proxy, captcha walls, etc.) run with `--scrape 0`. The synthetic generator in `src/scraper/synthetic.py` produces ~6,000 plausible NJ listings across all 21 counties with empirically-calibrated medians (Bergen ~$700k, Cumberland ~$220k, Hudson ~$650k, etc.) so the rest of the pipeline runs end-to-end and produces real (non-placeholder) outputs.

---

## 5. Configuration

Edit `config/config.yaml` to change:

- target counties (defaults to all 21)
- rate-limit seconds / max retries
- model hyperparameters (Ridge alpha grid, K-Means k range)
- micro-market thresholds (min listings to publish n, ZIP cluster minimum size)

---

## 6. Reproducibility

- All random seeds fixed (`config.yaml: random_seed: 42`)
- Scraper writes raw immutable CSV + Parquet snapshots with timestamp in filename
- Cleaning and modeling pipelines are deterministic given a fixed raw file
- Models serialized via `joblib`; reload examples in `notebooks/NJ_Housing_Analysis.ipynb`

---

## 7. Testing

```bash
pytest tests/ -v
```

Covers: outlier removal, property-type standardization, ZIP validation, price-heat-index math, hedonic feature pipeline shape.

---

## 8. Deliverables Checklist

- [x] Source code (Phases 1–9)
- [x] `requirements.txt`
- [x] `README.md`
- [x] Jupyter notebook
- [x] `outputs/pricing_matrix.csv`
- [x] `reports/data_quality_report.md`
- [x] `reports/model_evaluation_report.md`
- [x] `reports/summary_deck.pptx` (8 slides)
- [x] GitHub-ready repo structure

---

## 9. Known Limitations

- Live Zillow/Realtor/Redfin scraping is brittle (anti-bot, layout changes). Selectors in each scraper are isolated to a `PARSERS` dict at the top of the file for quick repair.
- Geocoding via Nominatim is rate-limited to 1 req/s — for the full ~6,000-listing run, plan ~2 hours or swap in Google Maps API (key field in `config.yaml`).
- Property-type taxonomy is collapsed to 5 canonical buckets; sub-types (e.g., "Brownstone") are merged into the nearest parent.

---

## 10. License

Internal / academic use. Do not redistribute scraped data.
