from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Self, runtime_checkable

import numpy as np
import pandas as pd
from numpy.typing import NDArray


@runtime_checkable
class TrainableModel(Protocol):
    """Estimator contract required by the baseline training pipeline."""

    def fit(self, features: pd.DataFrame, target: pd.Series) -> Self:
        """Fit the estimator and return it."""
        ...

    def predict(self, features: pd.DataFrame) -> NDArray[np.float64]:
        """Predict target values."""
        ...


@dataclass(frozen=True, slots=True)
class TrainingRequest:
    as_of_date: date
    features_version: str
    horizon: int = 12


@dataclass(frozen=True, slots=True)
class TrainingResult:
    model: TrainableModel
    metrics: Mapping[str, float]
    training_rows: int


def train(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    request: TrainingRequest,
) -> TrainingResult:
    """Train and evaluate the global production forecasting model."""
    del features, target, request
    raise NotImplementedError("Baseline training is implemented by F3-13")


__all__ = ["TrainableModel", "TrainingRequest", "TrainingResult", "train"]
