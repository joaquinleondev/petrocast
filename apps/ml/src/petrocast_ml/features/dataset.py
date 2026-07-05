"""Assemble model-ready frames from persisted features (contracts A and F).

Training (F3-13) and inference (F3-18) both start from rows read out of
``features.well_features`` — this module turns those rows into the supervised
matrix (features + horizon + observed target) or the prediction input
(features + horizon), without ever recomputing a feature. The target/horizon
convention is contract F (ADR-0030): ``as_of_date`` is the first unknown
month, so horizon ``h`` targets month ``as_of_date + (h - 1)``; months with no
observed actual simply produce no training row (no imputed targets).
"""

from collections.abc import Iterable

import pandas as pd

from petrocast_ml.features.schema import (
    HORIZON_COLUMN,
    KEY_COLUMNS,
    MAX_HORIZON,
    MODEL_INPUT_COLUMNS,
    STATIC_FEATURES,
    TARGET_COLUMN,
    TARGET_MONTH_COLUMN,
    validate_feature_frame,
)


def _checked_horizons(horizons: Iterable[int]) -> list[int]:
    checked = sorted({int(h) for h in horizons})
    if not checked:
        raise ValueError("at least one horizon is required")
    if checked[0] < 1 or checked[-1] > MAX_HORIZON:
        raise ValueError(f"horizons must lie within 1..{MAX_HORIZON} (contract F), got {checked}")
    return checked


def _with_horizons(features: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    replicas = []
    for horizon in horizons:
        replica = features.copy()
        replica[HORIZON_COLUMN] = horizon
        replica[TARGET_MONTH_COLUMN] = replica["as_of_date"] + pd.DateOffset(months=horizon - 1)
        replicas.append(replica)
    return pd.concat(replicas, ignore_index=True)


def build_training_dataset(
    features: pd.DataFrame,
    production: pd.DataFrame,
    *,
    horizons: Iterable[int] = range(1, MAX_HORIZON + 1),
) -> pd.DataFrame:
    """Join feature vectors with the observed targets of each horizon.

    ``features`` is a contract A frame (validated here); ``production`` is the
    (well_id, production_month, oil_prod_m3) series the targets come from.
    Returns one row per (well_id, as_of_date, horizon) whose target month was
    actually observed, carrying the full feature projection plus ``horizon``,
    ``target_month`` and ``oil_prod_m3_target``.
    """
    validate_feature_frame(features)
    expanded = _with_horizons(features, _checked_horizons(horizons))

    targets = production.loc[:, ["well_id", "production_month", "oil_prod_m3"]].rename(
        columns={"production_month": TARGET_MONTH_COLUMN, "oil_prod_m3": TARGET_COLUMN}
    )
    dataset = expanded.merge(targets, on=["well_id", TARGET_MONTH_COLUMN], how="inner")
    return dataset.sort_values([*KEY_COLUMNS, HORIZON_COLUMN], ignore_index=True)


def build_inference_frame(
    features: pd.DataFrame,
    *,
    horizon: int,
) -> pd.DataFrame:
    """Expand feature vectors into the prediction input for months 1..horizon.

    Returns one row per (well_id, as_of_date, horizon step) with the key
    columns, ``target_month`` (the month each step predicts) and every model
    input column — ready for :func:`as_model_input`. No feature is recomputed;
    unmaterialized cutoffs must be handled upstream (ADR-0031: serving does
    not compute features on demand).
    """
    if horizon < 1 or horizon > MAX_HORIZON:
        raise ValueError(f"horizon must lie within 1..{MAX_HORIZON} (contract F), got {horizon}")
    validate_feature_frame(features)
    expanded = _with_horizons(features, _checked_horizons(range(1, horizon + 1)))
    columns = [*KEY_COLUMNS, TARGET_MONTH_COLUMN, *MODEL_INPUT_COLUMNS]
    ordered = expanded.loc[:, columns]
    return ordered.sort_values([*KEY_COLUMNS, HORIZON_COLUMN], ignore_index=True)


def as_model_input(dataset: pd.DataFrame) -> pd.DataFrame:
    """Project the exact LightGBM input frame (contract F column order).

    Numeric features stay float; static attributes become pandas ``category``
    so the model treats them natively as categoricals. The same projection is
    used at training and at serving time — the model signature registered in
    MLflow (contract B) pins this exact set.
    """
    model_input = dataset.loc[:, list(MODEL_INPUT_COLUMNS)].copy()
    for column in STATIC_FEATURES:
        model_input[column] = model_input[column].astype("category")
    return model_input


__all__ = ["as_model_input", "build_inference_frame", "build_training_dataset"]
