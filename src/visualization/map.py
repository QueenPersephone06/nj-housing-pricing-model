"""Phase 9 — Interactive NJ choropleth map (Folium).

Loads NJ county GeoJSON (downloaded once into data/external/, but if it's
missing we synthesize a stub from county centroids so the pipeline never
breaks). Colors counties by median listing price, with hover tooltips
and a property-type filter.

Output:
    outputs/nj_housing_map.html
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
import pandas as pd
from folium.plugins import MarkerCluster

from src.utils.io import project_path, read_any
from src.utils.logger import get_logger

log = get_logger(__name__)


# Public-domain NJ county GeoJSON URL — used by setup script, but if not
# downloaded we fall back to a centroid stub.
COUNTY_CENTROIDS: dict[str, tuple[float, float]] = {
    "Atlantic": (39.46, -74.66), "Bergen": (40.96, -74.07), "Burlington": (39.87, -74.66),
    "Camden": (39.80, -74.96), "Cape May": (39.08, -74.83), "Cumberland": (39.33, -75.13),
    "Essex": (40.79, -74.24), "Gloucester": (39.71, -75.14), "Hudson": (40.73, -74.07),
    "Hunterdon": (40.57, -74.91), "Mercer": (40.29, -74.70), "Middlesex": (40.44, -74.41),
    "Monmouth": (40.29, -74.13), "Morris": (40.86, -74.55), "Ocean": (39.86, -74.25),
    "Passaic": (41.04, -74.30), "Salem": (39.57, -75.36), "Somerset": (40.56, -74.61),
    "Sussex": (41.13, -74.69), "Union": (40.66, -74.31), "Warren": (40.86, -75.00),
}


def _load_or_stub_geojson(cfg: dict[str, Any]) -> dict[str, Any]:
    path = project_path(cfg["paths"]["external_dir"], "nj_counties.geojson")
    if path.exists():
        return json.loads(path.read_text())
    log.warning("no county GeoJSON at %s — falling back to centroid markers only", path)
    return {"type": "FeatureCollection", "features": []}


def build_map(segmented_path: str | Path, cfg: dict[str, Any]) -> Path:
    df = read_any(segmented_path)
    medians = (
        df.groupby("county")
        .agg(median_price=("listing_price", "median"),
             n=("listing_price", "size"),
             median_ppsf=("price_per_sqft", "median"))
        .reset_index()
    )

    m = folium.Map(location=[40.2, -74.5], zoom_start=8, tiles="cartodbpositron")

    geojson = _load_or_stub_geojson(cfg)
    if geojson["features"]:
        folium.Choropleth(
            geo_data=geojson,
            data=medians,
            columns=["county", "median_price"],
            key_on="feature.properties.name",
            fill_color="YlGnBu",
            fill_opacity=0.75,
            line_opacity=0.4,
            legend_name="Median List Price ($)",
        ).add_to(m)
    else:
        # Fallback: large circle markers at centroids, sized by price
        max_price = medians["median_price"].max()
        for _, r in medians.iterrows():
            lat, lon = COUNTY_CENTROIDS.get(r["county"], (40.2, -74.5))
            radius = 8 + 28 * (r["median_price"] / max_price)
            folium.CircleMarker(
                location=(lat, lon),
                radius=radius,
                popup=(f"<b>{r['county']} County</b><br>"
                       f"Median: ${r['median_price']:,.0f}<br>"
                       f"Median $/sqft: ${r['median_ppsf']:,.0f}<br>"
                       f"Listings: {r['n']:,}"),
                color="#1B4F72",
                weight=1,
                fill=True,
                fill_color="#3498DB",
                fill_opacity=0.55,
            ).add_to(m)

    # Marker clusters per property type (toggleable layer controls = "filter")
    layer_groups: dict[str, folium.FeatureGroup] = {}
    for ptype in df["property_type"].dropna().unique():
        fg = folium.FeatureGroup(name=f"Listings — {ptype}", show=(ptype == "Single Family"))
        cluster = MarkerCluster().add_to(fg)
        sub = df[df["property_type"] == ptype].dropna(subset=["latitude", "longitude"]).head(1500)
        for _, r in sub.iterrows():
            folium.Marker(
                location=(r["latitude"], r["longitude"]),
                popup=(f"<b>${r['listing_price']:,.0f}</b><br>"
                       f"{r['full_address']}<br>"
                       f"{int(r['bedrooms'])}br · {r['bathrooms']}ba · "
                       f"{int(r['sqft']) if pd.notna(r['sqft']) else 'n/a'} sqft"),
                icon=folium.Icon(icon="home", prefix="fa"),
            ).add_to(cluster)
        layer_groups[ptype] = fg
        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    out_path = project_path(cfg["paths"]["outputs_dir"], "nj_housing_map.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    log.info("wrote interactive map: %s", out_path)
    return out_path
