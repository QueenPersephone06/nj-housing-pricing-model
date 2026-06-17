"""Phase 6 — Hedonic Pricing Model.

Linear Regression + Ridge with cross-validation. Logs MAE / RMSE / R²
on the held-out test set and a 5-fold CV. Persists both models to
outputs/models/ and writes reports/model_evaluation_report.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.utils.io import project_path, read_any
from src.utils.logger import get_logger

log = get_logger(__name__)

NUM_FEATURES = ["bedrooms", "bathrooms", "sqft", "lot_size", "year_built"]
CAT_FEATURES = ["county", "municipality", "property_type"]
TARGET = "listing_price"


def _build_pipeline(estimator) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CAT_FEATURES),
        ]
    )
    return Pipeline([("preprocess", preprocessor), ("model", estimator)])


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
    }


def _feature_importance(pipeline: Pipeline) -> pd.DataFrame:
    pre: ColumnTransformer = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    names: list[str] = []
    names.extend(NUM_FEATURES)
    ohe: OneHotEncoder = pre.named_transformers_["cat"]
    names.extend(ohe.get_feature_names_out(CAT_FEATURES).tolist())
    coefs = getattr(model, "coef_", None)
    if coefs is None:
        return pd.DataFrame()
    return (
        pd.DataFrame({"feature": names, "coefficient": coefs})
        .assign(abs_coef=lambda d: d["coefficient"].abs())
        .sort_values("abs_coef", ascending=False)
        .drop(columns="abs_coef")
        .reset_index(drop=True)
    )


def train_hedonic(segmented_path: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    df = read_any(segmented_path).copy()
    df = df.dropna(subset=[TARGET])
    df["year_built"] = df["year_built"].fillna(df["year_built"].median())
    df["lot_size"] = df["lot_size"].fillna(df["lot_size"].median())

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df[TARGET].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=cfg["modeling"]["test_size"], random_state=cfg["random_seed"]
    )
    kf = KFold(n_splits=cfg["modeling"]["cv_folds"], shuffle=True, random_state=cfg["random_seed"])

    models_dir = project_path(cfg["paths"]["models_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}

    # ---- Linear ---------------------------------------------------------
    lin = _build_pipeline(LinearRegression())
    lin.fit(X_train, y_train)
    pred = lin.predict(X_test)
    test_metrics = _metrics(y_test, pred)
    cv_r2 = cross_val_score(lin, X, y, cv=kf, scoring="r2")
    cv_mae = -cross_val_score(lin, X, y, cv=kf, scoring="neg_mean_absolute_error")
    results["linear"] = {
        "test_metrics": test_metrics,
        "cv_r2_mean": float(cv_r2.mean()),
        "cv_r2_std": float(cv_r2.std()),
        "cv_mae_mean": float(cv_mae.mean()),
    }
    joblib.dump(lin, models_dir / "linreg.joblib")
    _feature_importance(lin).to_csv(models_dir / "linreg_coefficients.csv", index=False)

    # ---- Ridge w/ alpha search ------------------------------------------
    best_alpha = None
    best_cv = -np.inf
    for a in cfg["modeling"]["ridge_alphas"]:
        ridge = _build_pipeline(Ridge(alpha=a, random_state=cfg["random_seed"]))
        cv = cross_val_score(ridge, X_train, y_train, cv=kf, scoring="r2").mean()
        if cv > best_cv:
            best_cv = cv
            best_alpha = a
    ridge = _build_pipeline(Ridge(alpha=best_alpha, random_state=cfg["random_seed"]))
    ridge.fit(X_train, y_train)
    pred = ridge.predict(X_test)
    results["ridge"] = {
        "best_alpha": best_alpha,
        "test_metrics": _metrics(y_test, pred),
        "cv_r2_mean": float(best_cv),
    }
    joblib.dump(ridge, models_dir / "ridge.joblib")
    _feature_importance(ridge).to_csv(models_dir / "ridge_coefficients.csv", index=False)

    # ---- Markdown report -------------------------------------------------
    report = _format_report(results, len(X_train), len(X_test))
    report_path = project_path(cfg["paths"]["reports_dir"], "model_evaluation_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    (models_dir / "metrics.json").write_text(json.dumps(results, indent=2))
    log.info("wrote model evaluation report → %s", report_path)
    return results


def _format_report(results: dict[str, Any], n_train: int, n_test: int) -> str:
    lines = [
        "# Model Evaluation Report",
        "",
        "_Hedonic pricing — Linear & Ridge regression on NJ active listings_",
        "",
        f"- Train set: **{n_train:,}** rows",
        f"- Test set:  **{n_test:,}** rows",
        f"- Features:  numerical = {NUM_FEATURES} · categorical = {CAT_FEATURES}",
        "",
        "## Linear Regression",
        "",
        f"- Test MAE:  ${results['linear']['test_metrics']['MAE']:,.0f}",
        f"- Test RMSE: ${results['linear']['test_metrics']['RMSE']:,.0f}",
        f"- Test R²:   {results['linear']['test_metrics']['R2']:.4f}",
        f"- 5-fold CV R² (mean ± std): {results['linear']['cv_r2_mean']:.4f} ± {results['linear']['cv_r2_std']:.4f}",
        f"- 5-fold CV MAE: ${results['linear']['cv_mae_mean']:,.0f}",
        "",
        "## Ridge Regression",
        "",
        f"- Best α (grid search): **{results['ridge']['best_alpha']}**",
        f"- Test MAE:  ${results['ridge']['test_metrics']['MAE']:,.0f}",
        f"- Test RMSE: ${results['ridge']['test_metrics']['RMSE']:,.0f}",
        f"- Test R²:   {results['ridge']['test_metrics']['R2']:.4f}",
        f"- 5-fold CV R²: {results['ridge']['cv_r2_mean']:.4f}",
        "",
        "Coefficients (top by absolute value) are persisted in `outputs/models/{linreg,ridge}_coefficients.csv`.",
        "Both pipelines are serialized to joblib for direct reuse: `outputs/models/linreg.joblib` and `outputs/models/ridge.joblib`.",
    ]
    return "\n".join(lines)
