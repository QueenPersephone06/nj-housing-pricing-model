"""Phase 8 — Visualizations.

Produces:
    1. County median price bar chart
    2. Price distribution histogram (overall + by corridor)
    3. Price/sqft by county (boxplot)
    4. Bedroom configuration analysis (median price vs beds)
    5. Property type analysis
    6. Heatmap (county × property_type, median price)
    7. Correlation matrix

All as PNG files under reports/figures/ + interactive Plotly HTML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import seaborn as sns

from src.utils.io import project_path, read_any
from src.utils.logger import get_logger

log = get_logger(__name__)


def _fig_dir(cfg: dict[str, Any]) -> Path:
    d = project_path(cfg["paths"]["figures_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_all_charts(segmented_path: str | Path, cfg: dict[str, Any]) -> list[Path]:
    df = read_any(segmented_path)
    sns.set_theme(style="whitegrid", context="talk")
    outputs: list[Path] = []
    figdir = _fig_dir(cfg)

    # ---- 1. County median price bar -------------------------------------
    medians = df.groupby("county")["listing_price"].median().sort_values()
    fig, ax = plt.subplots(figsize=(11, 7))
    medians.plot(kind="barh", ax=ax, color=sns.color_palette("crest", len(medians)))
    ax.set(xlabel="median list price (USD)", ylabel="", title="NJ — Median Listing Price by County")
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    fig.tight_layout()
    p = figdir / "01_county_median_bar.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 2. Price distribution histogram --------------------------------
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.hist(df["listing_price"].clip(upper=2_500_000), bins=60, color="#2C7FB8", alpha=0.85)
    ax.set(xlabel="listing price (USD, capped at $2.5M)", ylabel="count",
           title="Listing Price Distribution (NJ)")
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    fig.tight_layout()
    p = figdir / "02_price_histogram.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 3. Price/sqft by county ----------------------------------------
    fig, ax = plt.subplots(figsize=(13, 7))
    order = (df.groupby("county")["price_per_sqft"].median().sort_values().index.tolist())
    sns.boxplot(data=df, x="county", y="price_per_sqft", order=order, ax=ax,
                showfliers=False, palette="crest")
    ax.set(title="Price per Sqft by County", xlabel="", ylabel="$ / sqft")
    ax.tick_params(axis="x", rotation=70)
    fig.tight_layout()
    p = figdir / "03_price_per_sqft_by_county.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 4. Bedroom configuration ---------------------------------------
    bed_med = df.groupby(df["bedrooms"].round().clip(0, 6))["listing_price"].median()
    fig, ax = plt.subplots(figsize=(9, 5))
    bed_med.plot(kind="bar", ax=ax, color="#41B6C4")
    ax.set(xlabel="bedrooms", ylabel="median price", title="Median Price by Bedroom Count")
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    fig.tight_layout()
    p = figdir / "04_bedroom_config.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 5. Property type analysis --------------------------------------
    pt_summary = df.groupby("property_type").agg(
        median_price=("listing_price", "median"),
        n=("listing_price", "size"),
    ).sort_values("median_price")
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(pt_summary.index, pt_summary["median_price"], color=sns.color_palette("flare", len(pt_summary)))
    ax.set(title="Median Price by Property Type", ylabel="median price")
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    for bar, n in zip(bars, pt_summary["n"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"n={n}",
                ha="center", va="bottom", fontsize=10)
    fig.tight_layout()
    p = figdir / "05_property_type.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 6. Heatmap (county × property type) ----------------------------
    pivot = df.pivot_table(index="county", columns="property_type",
                           values="listing_price", aggfunc="median")
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(pivot / 1000, annot=True, fmt=".0f", cmap="YlGnBu",
                cbar_kws={"label": "median price ($k)"}, ax=ax)
    ax.set(title="Median Price ($k) — County × Property Type")
    fig.tight_layout()
    p = figdir / "06_heatmap_county_proptype.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 7. Correlation matrix ------------------------------------------
    num_cols = ["listing_price", "bedrooms", "bathrooms", "sqft", "lot_size",
                "year_built", "days_on_market", "price_per_sqft"]
    corr = df[num_cols].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Numerical Feature Correlation")
    fig.tight_layout()
    p = figdir / "07_correlation_matrix.png"
    fig.savefig(p, dpi=130); plt.close(fig); outputs.append(p)

    # ---- 8. Interactive Plotly box: median price by corridor ------------
    fig = px.box(df.assign(price_k=df["listing_price"] / 1000),
                 x="corridor", y="price_k", color="property_type",
                 title="Listing Price by Corridor & Property Type",
                 labels={"price_k": "price ($k)"})
    p_html = figdir / "08_price_by_corridor.html"
    fig.write_html(p_html, include_plotlyjs="cdn")
    outputs.append(p_html)

    log.info("wrote %d chart files to %s", len(outputs), figdir)
    return outputs
