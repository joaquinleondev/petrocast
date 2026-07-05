"""Pandas mirror of the ``well_features`` dbt model — the executable PIT spec.

This module re-states, feature by feature, what
``apps/data/dbt/models/features/well_features.sql`` computes, so the
point-in-time rule of contract A (ADR-0031) can be tested without a database:
the pytest suite recomputes a cutoff with and without the months after it and
asserts nothing changes, and pins the committed ``well_features.csv`` fixture
(hand-verified against the SQL) to these definitions.

It is NOT a serving or training path. The dbt model is the only writer of the
feature store and consumers read the persisted table (training-serving skew is
avoided by construction, ADR-0031). If you change a definition here, you are
changing contract A: change the SQL, the ``schema.yml`` docs and the fixture
in the same PR.
"""

import math
from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd

from petrocast_ml.features.schema import FEATURE_TABLE_COLUMNS, STATIC_FEATURES

_LAG_MONTHS = (1, 2, 3)


def _month_floor(value: date | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("M").to_timestamp()


def _months_between(later: pd.Timestamp, earlier: pd.Timestamp) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _window(known: pd.DataFrame, as_of: pd.Timestamp, months: int) -> pd.Series:
    """Observed production inside the ``months`` calendar months before ``as_of``."""
    start = as_of - pd.DateOffset(months=months)
    values = known.loc[known["production_month"] >= start, "oil_prod_m3"]
    return values.astype(float)


def _trend_slope(known: pd.DataFrame, as_of: pd.Timestamp, months: int) -> float:
    """OLS slope (m³/month) of production vs. calendar month index in the window."""
    start = as_of - pd.DateOffset(months=months)
    window = known.loc[known["production_month"] >= start]
    if len(window) < 2:
        return math.nan
    month_index = window["production_month"].dt.year * 12 + window["production_month"].dt.month
    slope, _ = np.polyfit(month_index.to_numpy(float), window["oil_prod_m3"].to_numpy(float), 1)
    return float(slope)


def _well_row(known: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, object]:
    by_month: Mapping[pd.Timestamp, float] = dict(
        zip(known["production_month"], known["oil_prod_m3"].astype(float), strict=True)
    )
    lags = {
        f"oil_prod_m3_lag_{k}m": by_month.get(as_of - pd.DateOffset(months=k), math.nan)
        for k in _LAG_MONTHS
    }

    window_3m = _window(known, as_of, 3)
    window_6m = _window(known, as_of, 6)
    roll_mean_3m = float(window_3m.mean()) if len(window_3m) else math.nan
    roll_mean_6m = float(window_6m.mean()) if len(window_6m) else math.nan
    roll_std_6m = float(window_6m.std(ddof=1)) if len(window_6m) >= 2 else math.nan
    ratio_3m_6m = roll_mean_3m / roll_mean_6m if roll_mean_6m else math.nan

    first_observed = known["production_month"].iloc[0]
    last_observed = known["production_month"].iloc[-1]
    return {
        "as_of_date": as_of,
        **lags,
        "oil_prod_m3_roll_mean_3m": roll_mean_3m,
        "oil_prod_m3_roll_mean_6m": roll_mean_6m,
        "oil_prod_m3_roll_std_6m": roll_std_6m,
        "oil_prod_m3_delta_1m": lags["oil_prod_m3_lag_1m"] - lags["oil_prod_m3_lag_2m"],
        "oil_prod_m3_ratio_3m_6m": ratio_3m_6m,
        "oil_prod_m3_trend_slope_6m": _trend_slope(known, as_of, 6),
        "oil_prod_m3_trend_slope_12m": _trend_slope(known, as_of, 12),
        "zero_months_last_6m": int((window_6m == 0).sum()),
        "months_with_history": len(known),
        "well_age_months": _months_between(as_of, first_observed),
        "months_since_last_observed": _months_between(as_of, last_observed),
        "last_observed_month": last_observed,
    }


def compute_well_features(
    production: pd.DataFrame,
    *,
    as_of_date: date | pd.Timestamp,
    well_attributes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Recompute the contract A feature vectors for one knowledge cutoff.

    ``production`` carries the (well_id, production_month, oil_prod_m3) series
    at pozo-mes grain; ``well_attributes`` optionally carries the static
    columns of ``gold.dim_well`` (well_id, basin, field, resource_type). The
    cutoff is floored to the first day of its month, and only months strictly
    before it are used — by construction, exactly like the dbt model. Wells
    with no history before the cutoff produce no row.
    """
    as_of = _month_floor(as_of_date)
    known_all = production.loc[production["production_month"] < as_of]

    rows: list[dict[str, object]] = []
    for well_id, known in known_all.groupby("well_id", sort=True):
        rows.append(
            {"well_id": str(well_id), **_well_row(known.sort_values("production_month"), as_of)}
        )
    if not rows:
        return pd.DataFrame(columns=list(FEATURE_TABLE_COLUMNS))

    features = pd.DataFrame(rows)
    if well_attributes is not None:
        statics = well_attributes.loc[:, ["well_id", *STATIC_FEATURES]]
        features = features.merge(statics, on="well_id", how="left")
    else:
        features.loc[:, list(STATIC_FEATURES)] = pd.NA

    return features.loc[:, list(FEATURE_TABLE_COLUMNS)].reset_index(drop=True)


__all__ = ["compute_well_features"]
