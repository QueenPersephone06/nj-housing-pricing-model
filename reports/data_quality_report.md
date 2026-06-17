# Data Quality Report

_Generated automatically by `src/cleaning/clean.py`._

## Pipeline metrics

- **input_rows**: 6017
- **duplicates_removed**: 0
- **price_outliers_removed**: 5
- **invalid_zips_dropped**: 0
- **invalid_counties_dropped**: 0
- **output_rows**: 6012
- **completeness_pct**: 95.80089820359281

## Per-column completeness

| column | missing % | unique values |
|---|---:|---:|
| `listing_price` | 0.00% | 4,284 |
| `full_address` | 0.00% | 6,012 |
| `zip_code` | 0.00% | 109 |
| `county` | 0.00% | 21 |
| `municipality` | 0.00% | 112 |
| `bedrooms` | 0.00% | 13 |
| `bathrooms` | 0.00% | 5,368 |
| `sqft` | 0.00% | 2,329 |
| `property_type` | 0.00% | 5 |
| `listing_url` | 0.00% | 6,012 |
| `scrape_timestamp` | 0.00% | 5,205 |
| `lot_size` | 18.85% | 3,967 |
| `year_built` | 2.81% | 133 |
| `days_on_market` | 0.00% | 196 |
| `hoa_fees` | 62.33% | 627 |
| `source` | 0.00% | 1 |
| `price_per_sqft` | 0.00% | 5,995 |
| `bedrooms_was_missing` | 0.00% | 2 |
| `bathrooms_was_missing` | 0.00% | 2 |
| `sqft_was_missing` | 0.00% | 2 |

## County coverage

| county | n listings |
|---|---:|
| Bergen | 326 |
| Passaic | 324 |
| Gloucester | 322 |
| Camden | 316 |
| Essex | 307 |
| Mercer | 305 |
| Monmouth | 304 |
| Somerset | 302 |
| Salem | 302 |
| Ocean | 295 |
| Middlesex | 295 |
| Atlantic | 292 |
| Hudson | 285 |
| Burlington | 265 |
| Hunterdon | 264 |
| Warren | 260 |
| Cumberland | 258 |
| Union | 254 |
| Sussex | 250 |
| Morris | 248 |
| Cape May | 238 |

✅ All 21 NJ counties covered.

## Property-type distribution

| type | n |
|---|---:|
| Single Family | 3,670 |
| Condo/Co-op | 1,133 |
| Townhouse | 615 |
| Multi-Family | 425 |
| Land | 169 |