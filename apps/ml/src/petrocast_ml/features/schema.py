"""Frozen projection of the feature store table (contract A, ADR-0031).

Single source of truth for the column names, grouping and order that training
(F3-13) and inference (F3-18) read from ``features.well_features``. The dbt
model in ``apps/data/dbt/models/features/well_features.sql`` is the only
writer; consumers import these constants instead of hardcoding column lists so
a contract drift fails loudly at validation time, not silently at predict
time. The surrogate ``feature_key`` is intentionally not part of the
projection (it exists for idempotent re-materialization, not for consumers).
"""

from typing import Final

import pandas as pd

# Logical primary key of the store: what was known about a well at a cutoff.
KEY_COLUMNS: Final[tuple[str, ...]] = ("well_id", "as_of_date")

# Point-in-time lags: production of the k-th month before as_of_date (m³).
LAG_FEATURES: Final[tuple[str, ...]] = (
    "oil_prod_m3_lag_1m",
    "oil_prod_m3_lag_2m",
    "oil_prod_m3_lag_3m",
)

# Rolling aggregates over observed months in the window before as_of_date.
ROLLING_FEATURES: Final[tuple[str, ...]] = (
    "oil_prod_m3_roll_mean_3m",
    "oil_prod_m3_roll_mean_6m",
    "oil_prod_m3_roll_std_6m",
)

# Trend / momentum: decline direction and speed of the recent series.
TREND_FEATURES: Final[tuple[str, ...]] = (
    "oil_prod_m3_delta_1m",
    "oil_prod_m3_ratio_3m_6m",
    "oil_prod_m3_trend_slope_6m",
    "oil_prod_m3_trend_slope_12m",
)

# History shape: intermittency, depth of history, age and staleness.
HISTORY_FEATURES: Final[tuple[str, ...]] = (
    "zero_months_last_6m",
    "months_with_history",
    "well_age_months",
    "months_since_last_observed",
)

# Static well attributes (cold-start features, ADR-0030). Categorical.
STATIC_FEATURES: Final[tuple[str, ...]] = ("basin", "field", "resource_type")

NUMERIC_FEATURES: Final[tuple[str, ...]] = (
    *LAG_FEATURES,
    *ROLLING_FEATURES,
    *TREND_FEATURES,
    *HISTORY_FEATURES,
)

# Every feature the model consumes, before the horizon input is attached.
FEATURE_COLUMNS: Final[tuple[str, ...]] = (*NUMERIC_FEATURES, *STATIC_FEATURES)

# Audit column: lets serving explain staleness; never fed to the model.
AUDIT_COLUMNS: Final[tuple[str, ...]] = ("last_observed_month",)

# Column order of the persisted table projection, as the dbt model selects it.
FEATURE_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    *KEY_COLUMNS,
    *LAG_FEATURES,
    *ROLLING_FEATURES,
    *TREND_FEATURES,
    *HISTORY_FEATURES,
    *AUDIT_COLUMNS,
    *STATIC_FEATURES,
)

# Contract F (ADR-0030): direct multi-step strategy — one global model with
# the horizon as an input; as_of_date is the first unknown month, so horizon h
# targets month as_of_date + (h - 1).
HORIZON_COLUMN: Final[str] = "horizon"
TARGET_MONTH_COLUMN: Final[str] = "target_month"
TARGET_COLUMN: Final[str] = "oil_prod_m3_target"
MAX_HORIZON: Final[int] = 12

# Exact input frame the LightGBM model sees (training and serving alike).
MODEL_INPUT_COLUMNS: Final[tuple[str, ...]] = (*FEATURE_COLUMNS, HORIZON_COLUMN)


def validate_feature_frame(features: pd.DataFrame) -> pd.DataFrame:
    """Check a frame read from the store against contract A; return it as-is.

    Raises ``ValueError`` listing every violation: missing columns, null or
    duplicated keys, and point-in-time breaches (a row whose newest observed
    month is not strictly before its own cutoff).
    """
    problems: list[str] = []

    missing = [column for column in FEATURE_TABLE_COLUMNS if column not in features.columns]
    if missing:
        problems.append(f"missing columns: {missing}")
    else:
        keys = features.loc[:, list(KEY_COLUMNS)]
        if keys.isna().any().any():
            problems.append("null values in key columns (well_id, as_of_date)")
        if keys.duplicated().any():
            problems.append("duplicated (well_id, as_of_date) keys")
        pit_violations = features["last_observed_month"] >= features["as_of_date"]
        if pit_violations.any():
            offenders = features.loc[pit_violations, "well_id"].tolist()
            problems.append(
                f"point-in-time violation (last_observed_month >= as_of_date): {offenders}"
            )
        if (features["months_since_last_observed"] < 1).any():
            problems.append("months_since_last_observed below 1 contradicts the point-in-time rule")

    if problems:
        raise ValueError("feature frame violates contract A: " + "; ".join(problems))
    return features


__all__ = [
    "AUDIT_COLUMNS",
    "FEATURE_COLUMNS",
    "FEATURE_TABLE_COLUMNS",
    "HISTORY_FEATURES",
    "HORIZON_COLUMN",
    "KEY_COLUMNS",
    "LAG_FEATURES",
    "MAX_HORIZON",
    "MODEL_INPUT_COLUMNS",
    "NUMERIC_FEATURES",
    "ROLLING_FEATURES",
    "STATIC_FEATURES",
    "TARGET_COLUMN",
    "TARGET_MONTH_COLUMN",
    "TREND_FEATURES",
    "validate_feature_frame",
]
