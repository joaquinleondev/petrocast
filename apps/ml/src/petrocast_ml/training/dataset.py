"""Supervised dataset assembly from the feature store (F3-13).

Turns contract-A feature rows plus the raw production series into training
examples following contract F (ADR-0030): with ``as_of_date`` the first
unknown month, horizon ``h`` targets month ``as_of_date + (h - 1)`` ("train
through M, predict M+1 … M+h"). Months without an observed actual produce no
row — targets are never imputed. Each row also carries the persistence
baseline (last observed value strictly before the cutoff, ADR-0030) so model
and naive are always evaluated on exactly the same split.
"""

from dataclasses import dataclass

import pandas as pd

from petrocast_ml.features import validate_feature_frame
from petrocast_ml.training.contracts import TrainingRequest

TARGET_COLUMN = "oil_prod_m3_target"
NAIVE_COLUMN = "naive_forecast_m3"
HORIZON_COLUMN = "horizon"


def build_training_dataset(
    well_features: pd.DataFrame,
    production: pd.DataFrame,
    *,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    """Build one supervised row per (well_id, as_of_date, horizon) with target.

    ``production`` needs columns (well_id, production_month, oil_prod_m3) at
    the pozo-mes grain of gold.fact_production.
    """
    if not horizons or min(horizons) < 1 or max(horizons) > 12:
        raise ValueError(f"horizons must be within 1..12 (contract F), got {horizons!r}")

    features = validate_feature_frame(well_features)

    per_horizon = []
    for horizon in sorted(horizons):
        frame = features.copy()
        frame[HORIZON_COLUMN] = horizon
        frame["target_month"] = frame["as_of_date"] + pd.DateOffset(months=horizon - 1)
        per_horizon.append(frame)
    expanded = pd.concat(per_horizon, ignore_index=True)

    targets = production.rename(
        columns={"production_month": "target_month", "oil_prod_m3": TARGET_COLUMN}
    )
    expanded = expanded.merge(targets, on=["well_id", "target_month"], how="left")
    # Unobserved target months yield no training row (contract F: no imputation).
    expanded = expanded.loc[expanded[TARGET_COLUMN].notna()].reset_index(drop=True)

    naive = pd.merge_asof(
        expanded.sort_values("as_of_date"),
        production.rename(columns={"oil_prod_m3": NAIVE_COLUMN}).sort_values("production_month"),
        left_on="as_of_date",
        right_on="production_month",
        by="well_id",
        direction="backward",
        allow_exact_matches=False,  # strictly before the knowledge cutoff
    )
    return (
        naive.drop(columns=["production_month"])
        .sort_values(["as_of_date", "well_id", HORIZON_COLUMN])
        .reset_index(drop=True)
    )


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    """Chronological train/validation/test partition of a training dataset."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def temporal_split(dataset: pd.DataFrame, *, request: TrainingRequest) -> TemporalSplit:
    """Split by knowledge cutoff, never randomly (ADR-0030).

    Test = the single-origin evaluation cutoff ``request.as_of_date``;
    validation = the ``request.validation_cutoffs`` distinct cutoffs right
    before it; train = everything older.
    """
    test_cutoff = pd.Timestamp(request.as_of_date)
    cutoffs = sorted(dataset["as_of_date"].unique())
    if test_cutoff not in cutoffs:
        raise ValueError(f"no dataset rows for evaluation cutoff {request.as_of_date}")

    earlier = [cutoff for cutoff in cutoffs if cutoff < test_cutoff]
    validation_count = min(request.validation_cutoffs, len(earlier))
    validation_set = set(earlier[len(earlier) - validation_count :]) if validation_count else set()
    train_set = set(earlier) - validation_set
    if not train_set:
        raise ValueError(
            f"no training cutoffs older than {request.as_of_date} "
            f"(validation_cutoffs={request.validation_cutoffs})"
        )

    return TemporalSplit(
        train=dataset.loc[dataset["as_of_date"].isin(train_set)].reset_index(drop=True),
        validation=dataset.loc[dataset["as_of_date"].isin(validation_set)].reset_index(drop=True),
        test=dataset.loc[dataset["as_of_date"] == test_cutoff].reset_index(drop=True),
    )


__all__ = [
    "HORIZON_COLUMN",
    "NAIVE_COLUMN",
    "TARGET_COLUMN",
    "TemporalSplit",
    "build_training_dataset",
    "temporal_split",
]
