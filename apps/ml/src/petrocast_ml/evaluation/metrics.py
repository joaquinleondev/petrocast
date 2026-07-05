"""Per-well backtesting metrics (F3-15, contract F).

Implements the metric semantics frozen in ADR-0030 over the single-origin
test split: MAE/RMSE in m³ pooled over horizons, MASE against the in-sample
one-step naive (successive observed rows — the convention frozen by the F3-10
fixture ``expected_naive_backtest.csv``), MAPE restricted to non-zero actuals
(in percent, the PRD vocabulary) and the p50/p75/p90 distribution view that
gates and report consume. Pure pandas/numpy — no I/O, no MLflow.
"""

from typing import Final

import numpy as np
import pandas as pd

from petrocast_ml.training.dataset import NAIVE_COLUMN, TARGET_COLUMN

PREDICTION_COLUMN: Final = "prediction_m3"

#: ADR-0030 eligibility filter: wells need this many observed months before
#: the cutoff to enter metrics and gates (no reliable Arps or seasonality below).
MIN_HISTORY_MONTHS: Final = 12

_QUANTILES: Final[dict[str, float]] = {"p50": 0.5, "p75": 0.75, "p90": 0.9}


def _observed_before(production: pd.DataFrame, as_of_date: pd.Timestamp) -> pd.DataFrame:
    return production.loc[
        (production["production_month"] < as_of_date) & production["oil_prod_m3"].notna()
    ]


def eligible_wells(production: pd.DataFrame, *, as_of_date: pd.Timestamp) -> list[str]:
    """Wells with >= MIN_HISTORY_MONTHS observed months strictly before the cutoff."""
    observed = _observed_before(production, as_of_date)
    counts = observed.groupby("well_id")["production_month"].nunique()
    return sorted(str(well_id) for well_id in counts.index[counts >= MIN_HISTORY_MONTHS])


def one_step_naive_mae(production: pd.DataFrame, *, as_of_date: pd.Timestamp) -> pd.Series:
    """MASE denominator per well: mean |Y_t − Y_{t−1}| over successive observed rows.

    Successive means successive observed months in chronological order —
    calendar gaps collapse (fixture-frozen convention). Wells with fewer than
    two observations produce no entry.
    """
    observed = _observed_before(production, as_of_date).sort_values(
        ["well_id", "production_month"]
    )
    diffs = observed.groupby("well_id")["oil_prod_m3"].diff().abs()
    return diffs.groupby(observed["well_id"]).mean().dropna()


def per_well_metrics(test: pd.DataFrame, *, insample_naive_mae: pd.Series) -> pd.DataFrame:
    """One metrics row per well over its evaluable test rows, pooled horizons.

    NaN encodes "undefined": MASE when the denominator is missing or zero,
    MAPE when the well has no positive actuals in the window.
    """
    evaluable = test.loc[test[NAIVE_COLUMN].notna()]
    index: list[str] = []
    rows: list[dict[str, float]] = []
    for well_id, group in evaluable.groupby("well_id"):
        model_abs = (group[TARGET_COLUMN] - group[PREDICTION_COLUMN]).abs()
        naive_abs = (group[TARGET_COLUMN] - group[NAIVE_COLUMN]).abs()
        positive = group.loc[group[TARGET_COLUMN] > 0]
        mape = (
            float(
                (
                    (positive[TARGET_COLUMN] - positive[PREDICTION_COLUMN]).abs()
                    / positive[TARGET_COLUMN]
                ).mean()
                * 100.0
            )
            if len(positive)
            else float("nan")
        )
        index.append(str(well_id))
        rows.append(
            {
                "model_mae_m3": float(model_abs.mean()),
                "model_rmse_m3": float(np.sqrt((model_abs**2).mean())),
                "naive_mae_m3": float(naive_abs.mean()),
                "mape_nonzero_pct": mape,
            }
        )
    metrics = pd.DataFrame(rows, index=pd.Index(index, name="well_id"))
    denominator = insample_naive_mae.reindex(metrics.index)
    metrics["mase"] = metrics["model_mae_m3"] / denominator.where(denominator > 0)
    return metrics


def distribution(values: pd.Series) -> dict[str, float]:
    """p50/p75/p90 over wells where the metric is defined; empty dict if none."""
    defined = values.dropna()
    if defined.empty:
        return {}
    return {name: float(defined.quantile(q)) for name, q in _QUANTILES.items()}


__all__ = [
    "MIN_HISTORY_MONTHS",
    "PREDICTION_COLUMN",
    "distribution",
    "eligible_wells",
    "one_step_naive_mae",
    "per_well_metrics",
]
