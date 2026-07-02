"""Baseline training pipeline (F3-13).

Implements the ``train()`` contract frozen in F3-07: temporal split by
knowledge cutoff (never random, ADR-0030), one global LightGBM fit on the
train cutoffs, and MAE/RMSE in m³ for both the model and the persistence
baseline on the same held-out test cutoff — the naive comparison the PRD KPI
and gate 2 are built on. Full evaluation (MASE, distribution, gates) lands in
F3-15; this module only guarantees the baseline is reproducible and honestly
split.
"""

import math
from typing import Any

import numpy as np
import pandas as pd

from petrocast_ml.training.contracts import TrainingRequest, TrainingResult
from petrocast_ml.training.dataset import (
    NAIVE_COLUMN,
    TARGET_COLUMN,
    TemporalSplit,
    temporal_split,
)
from petrocast_ml.training.model import create_model, prepare_model_input


def _mae(errors: pd.Series) -> float:
    return float(errors.abs().mean())


def _rmse(errors: pd.Series) -> float:
    return float(math.sqrt((errors**2).mean()))


def train(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    request: TrainingRequest,
    params: dict[str, Any] | None = None,
) -> TrainingResult:
    """Train and evaluate the global production forecasting model.

    ``features`` is a supervised dataset from ``build_training_dataset``
    (contract-A columns + horizon + naive baseline); ``target`` is its aligned
    target series in m³. Split, fit and evaluation all happen against
    ``request.as_of_date`` as the single-origin test cutoff (contract F).
    """
    dataset = features.copy()
    dataset[TARGET_COLUMN] = target.to_numpy()
    split = temporal_split(dataset, request=request)

    model = create_model(params)
    model.fit(prepare_model_input(split.train), split.train[TARGET_COLUMN])

    metrics = _evaluate(model, split)
    return TrainingResult(model=model, metrics=metrics, training_rows=len(split.train))


def _evaluate(model: Any, split: TemporalSplit) -> dict[str, float]:
    test = split.test
    predicted = np.asarray(model.predict(prepare_model_input(test)), dtype=float)
    model_errors = test[TARGET_COLUMN] - predicted
    # Persistence baseline on exactly the same rows: missing naive (well with no
    # pre-cutoff history) cannot happen for store-backed rows, but guard anyway.
    naive_errors = (test[TARGET_COLUMN] - test[NAIVE_COLUMN]).dropna()

    return {
        "model_mae_m3": _mae(model_errors),
        "model_rmse_m3": _rmse(model_errors),
        "naive_mae_m3": _mae(naive_errors),
        "naive_rmse_m3": _rmse(naive_errors),
        "train_rows": float(len(split.train)),
        "validation_rows": float(len(split.validation)),
        "test_rows": float(len(test)),
    }


__all__ = ["train"]
