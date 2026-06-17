"""Phase 7 — K-Means clustering on (price, price_per_sqft).

Picks k via the elbow method, then maps cluster centroids to ordered
tiers: Budget → Mid → Premium → Luxury (when k=4). For k≠4 the tier
list is truncated/padded sensibly.

Outputs
-------
- data/processed/listings_with_tier.parquet
- reports/figures/clustering_elbow.png
- reports/figures/clustering_scatter.png
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from src.utils.io import project_path, read_any, write_dataframe
from src.utils.logger import get_logger

log = get_logger(__name__)


def _elbow(X: np.ndarray, k_min: int, k_max: int, seed: int) -> int:
    inertias: list[float] = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)
        inertias.append(km.inertia_)
    # Knee = the k with the maximum 2nd-derivative drop
    if len(inertias) < 3:
        return k_min
    diffs = np.diff(inertias)
    second = np.diff(diffs)
    knee_idx = int(np.argmax(second)) + 1  # +1 to map back to k axis
    return k_min + knee_idx


def cluster_listings(segmented_path: str | Path, cfg: dict[str, Any]) -> Path:
    df = read_any(segmented_path).copy()
    feats = df[["listing_price", "price_per_sqft"]].dropna()
    scaler = StandardScaler()
    X = scaler.fit_transform(feats.values)

    k_min, k_max = cfg["clustering"]["k_min"], cfg["clustering"]["k_max"]
    seed = cfg["random_seed"]

    # Elbow plot
    inertias = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)
        inertias.append(km.inertia_)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(k_min, k_max + 1), inertias, marker="o")
    ax.set(xlabel="k", ylabel="inertia", title="K-Means Elbow")
    fig.tight_layout()
    figdir = project_path(cfg["paths"]["figures_dir"])
    figdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(figdir / "clustering_elbow.png", dpi=120)
    plt.close(fig)

    k = _elbow(X, k_min, k_max, seed)
    # Default to 4 to respect the Budget/Mid/Premium/Luxury spec unless the
    # elbow strongly disagrees.
    if abs(k - 4) <= 1:
        k = 4
    log.info("k-means: chose k=%d (elbow scan over [%d, %d])", k, k_min, k_max)

    km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)
    feats["cluster"] = km.labels_

    # Map cluster id → tier by ascending median price
    centroid_prices = (
        feats.groupby("cluster")["listing_price"].median().sort_values().reset_index()
    )
    tier_names = cfg["clustering"]["tier_names"]
    if k > len(tier_names):
        tier_names = tier_names + [f"Tier{i+1}" for i in range(k - len(tier_names))]
    cluster_to_tier = {row["cluster"]: tier_names[i] for i, row in centroid_prices.iterrows()}
    feats["tier"] = feats["cluster"].map(cluster_to_tier)

    df = df.merge(feats[["cluster", "tier"]], left_index=True, right_index=True, how="left")

    # Scatter plot
    fig, ax = plt.subplots(figsize=(8, 5))
    palette = plt.cm.viridis(np.linspace(0, 1, k))
    for i, tier in enumerate(tier_names[:k]):
        sub = df[df["tier"] == tier]
        ax.scatter(sub["sqft"], sub["listing_price"], s=8, alpha=0.45,
                   color=palette[i], label=tier)
    ax.set(xlabel="sqft", ylabel="listing price (USD)",
           title=f"K-Means tiers (k={k})")
    ax.legend(loc="upper left")
    ax.set_xlim(0, 6000)
    fig.tight_layout()
    fig.savefig(figdir / "clustering_scatter.png", dpi=120)
    plt.close(fig)

    out_stem = project_path(cfg["paths"]["processed_dir"], "listings_with_tier")
    written = write_dataframe(df, out_stem, csv=False, parquet=True)
    log.info("clustered: %d rows → %s", len(df), written["parquet"])
    return written["parquet"]
