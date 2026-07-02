"""Contract A as code: the feature-store projection ML consumers read (F3-11).

Mirrors the columns of ``features.well_features`` (ADR-0031, built by
``apps/data/dbt/models/features/well_features.sql``) minus the surrogate
``feature_key``, which is a warehouse implementation detail. Training (F3-13)
and inference (F3-18) validate every frame they read through
:func:`validate_feature_frame`, so a schema drift between the store and the
model fails loudly at the boundary instead of silently degrading predictions
(ADR-0031). All volumes are m³; trends are m³/month.
"""

from collections.abc import Callable
from enum import Enum
from typing import Any, Final

import pandas as pd


class FeatureKind(Enum):
    """Broad dtype family a contract column must satisfy."""

    NUMERIC = "numeric"
    DATE = "date"
    TEXT = "text"


#: Logical primary key of the store: idpozo as text + knowledge cutoff.
KEY_SCHEMA: Final[dict[str, FeatureKind]] = {
    "well_id": FeatureKind.TEXT,
    "as_of_date": FeatureKind.DATE,
}

#: Every persisted feature, in the canonical (model signature) order.
FEATURE_SCHEMA: Final[dict[str, FeatureKind]] = {
    "oil_prod_m3_lag_1m": FeatureKind.NUMERIC,
    "oil_prod_m3_lag_2m": FeatureKind.NUMERIC,
    "oil_prod_m3_lag_3m": FeatureKind.NUMERIC,
    "oil_prod_m3_lag_6m": FeatureKind.NUMERIC,
    "oil_prod_m3_lag_12m": FeatureKind.NUMERIC,
    "oil_prod_m3_roll_mean_3m": FeatureKind.NUMERIC,
    "oil_prod_m3_roll_mean_6m": FeatureKind.NUMERIC,
    "oil_prod_m3_roll_mean_12m": FeatureKind.NUMERIC,
    "oil_prod_m3_roll_std_6m": FeatureKind.NUMERIC,
    "oil_prod_m3_roll_std_12m": FeatureKind.NUMERIC,
    "oil_prod_m3_trend_6m": FeatureKind.NUMERIC,
    "oil_prod_m3_trend_12m": FeatureKind.NUMERIC,
    "months_with_history": FeatureKind.NUMERIC,
    "well_age_months": FeatureKind.NUMERIC,
    "months_since_last_observed": FeatureKind.NUMERIC,
    "zero_months_12m": FeatureKind.NUMERIC,
    "last_observed_month": FeatureKind.DATE,
    "basin": FeatureKind.TEXT,
    "field": FeatureKind.TEXT,
    "resource_type": FeatureKind.TEXT,
}

#: Full projection: keys first, then features, in canonical order.
CONTRACT_SCHEMA: Final[dict[str, FeatureKind]] = {**KEY_SCHEMA, **FEATURE_SCHEMA}

KEY_COLUMNS: Final[tuple[str, ...]] = tuple(KEY_SCHEMA)
FEATURE_COLUMNS: Final[tuple[str, ...]] = tuple(FEATURE_SCHEMA)
CONTRACT_COLUMNS: Final[tuple[str, ...]] = tuple(CONTRACT_SCHEMA)

_KIND_CHECKS: Final[dict[FeatureKind, Callable[[Any], bool]]] = {
    FeatureKind.NUMERIC: pd.api.types.is_numeric_dtype,
    FeatureKind.DATE: pd.api.types.is_datetime64_any_dtype,
    FeatureKind.TEXT: lambda dtype: (
        pd.api.types.is_string_dtype(dtype) or pd.api.types.is_object_dtype(dtype)
    ),
}


def validate_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a frame read from the store against contract A.

    Checks column presence (missing AND unexpected — signature drift must fail
    loudly, ADR-0031), dtype families, non-null keys and (well_id, as_of_date)
    uniqueness. Returns the frame reordered to the canonical column order so
    every consumer feeds the model the exact same signature.

    Raises:
        ValueError: describing every violation found, not just the first.
    """
    problems: list[str] = []

    missing = [column for column in CONTRACT_COLUMNS if column not in frame.columns]
    unexpected = [column for column in frame.columns if column not in CONTRACT_SCHEMA]
    if missing:
        problems.append(f"missing columns: {missing}")
    if unexpected:
        problems.append(f"unexpected columns: {unexpected}")

    for column, kind in CONTRACT_SCHEMA.items():
        if column in frame.columns and not _KIND_CHECKS[kind](frame[column].dtype):
            problems.append(f"column {column!r} is {frame[column].dtype}, expected {kind.value}")

    if not missing:
        keys = frame.loc[:, list(KEY_COLUMNS)]
        if keys.isna().any().any():
            problems.append("key columns contain nulls")
        if keys.duplicated().any():
            problems.append("duplicated (well_id, as_of_date) keys")

    if problems:
        raise ValueError("feature frame violates contract A: " + "; ".join(problems))
    return frame.loc[:, list(CONTRACT_COLUMNS)]


__all__ = [
    "CONTRACT_COLUMNS",
    "CONTRACT_SCHEMA",
    "FEATURE_COLUMNS",
    "FEATURE_SCHEMA",
    "KEY_COLUMNS",
    "KEY_SCHEMA",
    "FeatureKind",
    "validate_feature_frame",
]
