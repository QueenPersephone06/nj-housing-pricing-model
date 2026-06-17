"""IO helpers and config loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = PROJECT_ROOT / cfg_path
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def write_dataframe(df: pd.DataFrame, path: str | Path, *, csv: bool = True, parquet: bool = True) -> dict[str, Path]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    if csv:
        csv_path = p.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path
    if parquet:
        pq_path = p.with_suffix(".parquet")
        df.to_parquet(pq_path, index=False)
        outputs["parquet"] = pq_path
    return outputs


def read_any(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".csv":
        return pd.read_csv(p)
    raise ValueError(f"Unsupported file extension: {p.suffix}")
